"""Run the same account/UI tests against a disposable PostgreSQL schema in CI."""
import os
import uuid
from unittest import skip, skipUnless
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

import database as db
from test_accounts import AccountTests as _AccountTests


@skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL to run PostgreSQL integration tests')
class PostgreSQLTests(_AccountTests):
    def setUp(self):
        self.url = os.environ['TEST_DATABASE_URL']
        self.schema = 'expense_test_' + uuid.uuid4().hex
        with psycopg.connect(self.url) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        isolated_url = make_conninfo(self.url, options=f'-csearch_path={self.schema}')
        self.env_patch = patch.dict(os.environ, {'DATABASE_URL': isolated_url})
        self.env_patch.start()
        db.init_db()

    def tearDown(self):
        self.env_patch.stop()
        with psycopg.connect(self.url) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    @skip('Legacy files are migrated on SQLite before cloud import')
    def test_legacy_migration_does_not_give_records_to_first_signup(self):
        pass


# Avoid collecting the imported base case for a second time.
del _AccountTests
