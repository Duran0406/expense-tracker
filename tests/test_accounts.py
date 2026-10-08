import sqlite3
import os
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import auth
import database as db
from streamlit.testing.v1 import AppTest

PASSWORD = 'Test icin uzun bir sifre 2026!'
ROOT = Path(__file__).resolve().parents[1]


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {'DATABASE_URL': ''})
        self.env_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(db, 'DB_PATH', Path(self.temp.name) / 'test.db')
        self.path_patch.start()
        db.init_db()

    def tearDown(self):
        self.path_patch.stop()
        self.env_patch.stop()
        self.temp.cleanup()

    def register(self, username='alice'):
        return auth.register_user(username, PASSWORD)

    def add(self, user, amount=10.10, day=None, category=None):
        return db.add_expense(user['id'], amount, category or db.CATEGORIES[0],
                              db.PAYMENT_METHODS[0], 'Test expense', day or date.today())

    def test_password_hash_and_login(self):
        user = self.register('Alice')
        other = self.register('bob')
        with db.connection() as conn:
            hashes = [row['password_hash'] for row in conn.execute('SELECT password_hash FROM users')]
        self.assertNotEqual(hashes[0], hashes[1])
        self.assertTrue(all(PASSWORD not in value for value in hashes))
        self.assertEqual(auth.authenticate(' ALICE ', PASSWORD), user)
        self.assertIsNone(auth.authenticate('alice', 'This password is incorrect'))
        self.assertIsNone(auth.authenticate('missing', PASSWORD))
        with self.assertRaises(ValueError):
            self.register('ALICE')
        with self.assertRaises(ValueError):
            auth.register_user('empty', '')
        self.assertFalse(auth.verify_password('', hashes[0]))
        for username, password in [('tiny', 'a'), ('longer', 'x' * 129)]:
            registered = auth.register_user(username, password)
            self.assertEqual(auth.authenticate(username, password), registered)

    def test_throttle_survives_new_calls_and_expires(self):
        self.register()
        for _ in range(auth.MAX_FAILURES):
            self.assertIsNone(auth.authenticate('alice', 'Incorrect long password'))
        with self.assertRaisesRegex(ValueError, '15 dakika'):
            auth.authenticate('alice', PASSWORD)
        with patch('auth.time.time', return_value=time.time() + auth.LOGIN_WINDOW + 1):
            self.assertIsNotNone(auth.authenticate('alice', PASSWORD))

    def test_isolation_read_delete_and_filters(self):
        alice, bob = self.register(), self.register('bob')
        first = self.add(alice)
        self.add(alice, 20.20, date.today() - timedelta(days=1), db.CATEGORIES[1])
        self.add(bob, 999)
        rows = db.get_expenses(alice['id'], date.today() - timedelta(days=7), date.today())
        self.assertEqual(sum(r['amount_cents'] for r in rows), 3030)
        self.assertEqual(len(db.get_expenses(alice['id'], date.today(), date.today())), 1)
        self.assertEqual(len(db.get_expenses(alice['id'], date.today() - timedelta(days=7),
                                           date.today(), db.CATEGORIES[1])), 1)
        self.assertFalse(db.delete_expense(bob['id'], first))
        self.assertTrue(db.delete_expense(alice['id'], first))
        with self.assertRaises(ValueError):
            db.get_expenses(None, date.today(), date.today())
        for value in [-1, 0, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                self.add(alice, value)

    def test_online_payments_merge_without_changing_totals(self):
        user = self.register()
        expense_id = self.add(user, 123.45)
        with db.connection() as conn:
            conn.execute('UPDATE expenses SET payment_method = ? WHERE id = ?',
                         ('🌐 İnternet/Online', expense_id))
        db.init_db()
        db.init_db()
        rows = db.get_expenses(user['id'], date.today(), date.today())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['payment_method'], '💳 Kredi Kartı')
        self.assertEqual(rows[0]['amount_cents'], 12345)
        with self.assertRaises(ValueError):
            db.add_expense(user['id'], 10, db.CATEGORIES[0], '🌐 İnternet/Online', '', date.today())

    def test_legacy_migration_does_not_give_records_to_first_signup(self):
        with db.connection() as conn:
            conn.execute('DROP TABLE expenses')
            conn.execute('''CREATE TABLE expenses (id INTEGER PRIMARY KEY, amount REAL NOT NULL,
                category TEXT, payment_method TEXT, description TEXT, expense_date TEXT, created_at TEXT)''')
            conn.execute('INSERT INTO expenses VALUES (1, 12.34, ?, ?, ?, ?, ?)',
                         (db.CATEGORIES[0], db.PAYMENT_METHODS[0], 'Legacy', date.today().isoformat(), 'old'))
        db.init_db()
        db.init_db()
        stranger = self.register('stranger')
        self.assertEqual(db.get_expenses(stranger['id'], date.today(), date.today()), [])
        owner = self.register('duran')
        self.assertEqual(db.claim_legacy_expenses(owner['id']), 1)
        self.assertEqual(db.claim_legacy_expenses(stranger['id']), 0)
        rows = db.get_expenses(owner['id'], date.today(), date.today())
        self.assertEqual(rows[0]['amount_cents'], 1234)

    def test_demo_and_logout_do_not_touch_real_data(self):
        user = self.register()
        self.add(user)
        app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 0)
        next(b for b in app.button if b.label == '✨ Demo hesabını dene').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        self.assertEqual(len(app.get('plotly_chart')), 2)
        app.number_input[0].set_value(42.50)
        next(b for b in app.button if b.label == '💾 Kaydet').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(r['amount_cents'] == 4250 for r in app.session_state['demo_expenses']))
        next(b for b in app.button if b.label == 'Çıkış yap').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 0)
        self.assertEqual(len(db.get_expenses(user['id'], date.today(), date.today())), 1)

    def test_registration_login_add_delete_and_session_expiry(self):
        app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=20)
        app.text_input(key='register_username').set_value('newuser')
        app.text_input(key='register_password').set_value(PASSWORD)
        next(w for w in app.text_input if w.label == 'Şifreyi tekrar gir').set_value(PASSWORD)
        next(b for b in app.button if b.label == 'Hesap oluştur').click().run(timeout=20)
        self.assertFalse(app.exception)
        app.number_input[0].set_value(150.25)
        next(b for b in app.button if b.label == '💾 Kaydet').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, '150,25 ₺')
        next(b for b in app.button if b.label == '🗑️').click().run()
        next(b for b in app.button if b.label == 'Evet, sil').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, '0,00 ₺')
        next(b for b in app.button if b.label == 'Çıkış yap').click().run()
        app.text_input(key='login_username').set_value('newuser')
        app.text_input(key='login_password').set_value(PASSWORD)
        next(b for b in app.button if b.label == 'Giriş yap').click().run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        app.session_state['signed_in_at'] = time.time() - 9 * 60 * 60
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 0)


if __name__ == '__main__':
    unittest.main()
