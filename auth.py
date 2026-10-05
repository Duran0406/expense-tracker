"""Scrypt password hashes and persistent login throttling."""
import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from database import connection, INTEGRITY_ERRORS

LOGIN_WINDOW = 15 * 60
MAX_FAILURES = 5
_HASH_SLOT = threading.Semaphore(2)


def normalize_username(username):
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_]{3,30}', username):
        raise ValueError('Kullanıcı adı 3–30 karakter olmalı; a-z, 0-9 ve alt çizgi içerebilir.')
    return username


def _derive(password, salt):
    with _HASH_SLOT:
        return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=131072,
                              r=8, p=1, maxmem=256 * 1024 * 1024, dklen=32)


def hash_password(password):
    if not 15 <= len(password) <= 128:
        raise ValueError('Şifreniz 15–128 karakter olmalı. Uzun bir cümle kullanabilirsiniz.')
    salt = secrets.token_bytes(16)
    return f'scrypt$131072$8$1${salt.hex()}${_derive(password, salt).hex()}'


def verify_password(password, encoded):
    if not 15 <= len(password) <= 128:
        return False
    try:
        algorithm, n, r, p, salt, expected = encoded.split('$')
        if (algorithm, n, r, p) != ('scrypt', '131072', '8', '1'):
            return False
        return hmac.compare_digest(_derive(password, bytes.fromhex(salt)).hex(), expected)
    except (ValueError, TypeError):
        return False


def register_user(username, password):
    username = normalize_username(username)
    encoded = hash_password(password)
    try:
        with connection() as conn:
            cursor = conn.execute('INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?) RETURNING id',
                                  (username, encoded, datetime.now(timezone.utc).isoformat()))
            return {'id': cursor.fetchone()['id'], 'username': username}
    except INTEGRITY_ERRORS:
        raise ValueError('Bu kullanıcı adı kullanılamıyor. Başka bir ad seçin.') from None


def authenticate(username, password):
    username = normalize_username(username)
    now = time.time()
    # Reserve each attempt atomically, including attempts from concurrent sessions.
    with connection() as conn:
        conn.lock_login(username)
        conn.execute('DELETE FROM login_attempts WHERE window_start <= ?', (now - LOGIN_WINDOW,))
        attempt = conn.execute('SELECT failures FROM login_attempts WHERE username = ?', (username,)).fetchone()
        if attempt and attempt['failures'] >= MAX_FAILURES:
            raise ValueError('Çok fazla giriş denemesi yapıldı. 15 dakika sonra tekrar deneyin.')
        conn.execute('''INSERT INTO login_attempts(username, failures, window_start) VALUES (?, 1, ?)
            ON CONFLICT(username) DO UPDATE SET failures = login_attempts.failures + 1''', (username, now))
        row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    encoded = row['password_hash'] if row else 'scrypt$131072$8$1$' + '00' * 16 + '$' + '00' * 32
    valid = verify_password(password, encoded)
    if not row or not valid:
        return None
    with connection() as conn:
        conn.execute('DELETE FROM login_attempts WHERE username = ?', (username,))
    return {'id': row['id'], 'username': row['username']}
