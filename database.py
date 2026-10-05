"""SQLite locally, PostgreSQL in the cloud; every expense query is owner-scoped."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo
import psycopg
from psycopg.rows import dict_row

DB_PATH = Path(os.environ.get('EXPENSE_DB_PATH', Path(__file__).with_name('harcamalar.db')))
CATEGORIES = ['🍔 Yemek', '🛒 Market', '🚌 Ulaşım', '🏠 Fatura', '👕 Giyim', '🎮 Eğlence', '📚 Eğitim', '💊 Sağlık', '🎁 Hediye', '📦 Diğer']
PAYMENT_METHODS = ['💳 Kredi Kartı', '💵 Nakit', '🌐 İnternet/Online']
INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)


def local_today():
    return datetime.now(ZoneInfo('Europe/Istanbul')).date()


class DatabaseConnection:
    def __init__(self, raw, postgres=False):
        self.raw = raw
        self.postgres = postgres

    def execute(self, query, params=()):
        # All query text is application-owned; values always remain bound parameters.
        if self.postgres:
            query = query.replace('?', '%s')
        return self.raw.execute(query, params)

    def lock_login(self, username):
        if self.postgres:
            self.execute('SELECT pg_advisory_xact_lock(hashtextextended(?, 0))', (username,))
        else:
            self.execute('BEGIN IMMEDIATE')


@contextmanager
def connection():
    url = os.environ.get('DATABASE_URL', '').strip()
    if url:
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=15) as conn:
            yield DatabaseConnection(conn, postgres=True)
        return
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        with conn:
            yield DatabaseConnection(conn)
    finally:
        conn.close()


def init_db():
    if not os.environ.get('DATABASE_URL', '').strip():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connection() as conn:
        if conn.postgres:
            conn.execute('SELECT pg_advisory_xact_lock(84051001)')
            conn.execute('''CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, created_at TEXT NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS login_attempts (
                username TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start DOUBLE PRECISION NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS expenses (
                id BIGSERIAL PRIMARY KEY, amount DOUBLE PRECISION NOT NULL,
                category TEXT NOT NULL, payment_method TEXT NOT NULL, description TEXT,
                expense_date TEXT NOT NULL, created_at TEXT NOT NULL,
                user_id BIGINT NOT NULL REFERENCES users(id),
                amount_cents BIGINT NOT NULL CHECK(amount_cents > 0))''')
            conn.execute('CREATE INDEX IF NOT EXISTS expenses_owner_date ON expenses(user_id, expense_date)')
            return
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS login_attempts (
            username TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start REAL NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL,
            category TEXT NOT NULL, payment_method TEXT NOT NULL, description TEXT,
            expense_date TEXT NOT NULL, created_at TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0))''')
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(expenses)')}
        if 'user_id' not in columns:
            conn.execute('ALTER TABLE expenses ADD COLUMN user_id INTEGER REFERENCES users(id)')
        if 'amount_cents' not in columns:
            conn.execute('ALTER TABLE expenses ADD COLUMN amount_cents INTEGER')
            conn.execute('UPDATE expenses SET amount_cents = CAST(ROUND(amount * 100) AS INTEGER)')
        conn.execute('CREATE INDEX IF NOT EXISTS expenses_owner_date ON expenses(user_id, expense_date)')


def _owner(user_id):
    if type(user_id) is not int or user_id <= 0:
        raise ValueError('Geçerli bir kullanıcıyla giriş yapmalısınız.')


def get_user(user_id):
    _owner(user_id)
    with connection() as conn:
        row = conn.execute('SELECT id, username FROM users WHERE id = ?', (user_id,)).fetchone()
    return dict(row) if row else None


def validate_expense(amount, category, payment_method, description, expense_date):
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or not Decimal('0.01') <= value <= Decimal('1000000000'):
            raise ValueError('Tutar 0,01 ile 1.000.000.000 ₺ arasında olmalıdır.')
        cents = int((value * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError):
        raise ValueError('Geçerli bir tutar girin.') from None
    if category not in CATEGORIES or payment_method not in PAYMENT_METHODS:
        raise ValueError('Geçerli bir kategori ve ödeme yöntemi seçin.')
    if not isinstance(description, str) or len(description) > 500:
        raise ValueError('Açıklama en fazla 500 karakter olabilir.')
    if type(expense_date) is not date or expense_date > local_today():
        raise ValueError('Bugün veya geçmiş bir tarih seçin.')
    return cents


def add_expense(user_id, amount, category, payment_method, description, expense_date):
    _owner(user_id)
    cents = validate_expense(amount, category, payment_method, description, expense_date)
    with connection() as conn:
        cursor = conn.execute('''INSERT INTO expenses
            (user_id, amount, amount_cents, category, payment_method, description, expense_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id''',
            (user_id, cents / 100, cents, category, payment_method, description.strip(),
             expense_date.isoformat(), datetime.now(timezone.utc).isoformat()))
        return cursor.fetchone()['id']


def get_expenses(user_id, start_date, end_date, category=None):
    _owner(user_id)
    if start_date > end_date:
        raise ValueError('Başlangıç tarihi bitiş tarihinden sonra olamaz.')
    query = '''SELECT id, amount_cents, category, payment_method, description, expense_date
               FROM expenses WHERE user_id = ? AND expense_date BETWEEN ? AND ?'''
    params = [user_id, start_date.isoformat(), end_date.isoformat()]
    if category:
        query += ' AND category = ?'
        params.append(category)
    query += ' ORDER BY expense_date DESC, created_at DESC, id DESC'
    with connection() as conn:
        return [dict(row) for row in conn.execute(query, params)]


def delete_expense(user_id, expense_id):
    _owner(user_id)
    with connection() as conn:
        return conn.execute('DELETE FROM expenses WHERE id = ? AND user_id = ?',
                            (expense_id, user_id)).rowcount == 1


def claim_legacy_expenses(user_id):
    """Local administrator operation; never called by the public registration UI."""
    if not get_user(user_id):
        raise ValueError('Kullanıcı bulunamadı.')
    with connection() as conn:
        return conn.execute('UPDATE expenses SET user_id = ? WHERE user_id IS NULL', (user_id,)).rowcount
