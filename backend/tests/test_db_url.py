"""DATABASE_URL normalisation, masking and pool selection."""

import os
import subprocess
import sys

from sqlalchemy.pool import NullPool

from db_url import database_warnings, engine_kwargs, mask_database_url, normalize_database_url

POOLER = "postgres://postgres.abcd:s3cr3t-pw@aws-0-eu-west-3.pooler.supabase.com:{port}/postgres"


def test_postgres_scheme_and_sslmode_added():
    url = normalize_database_url(POOLER.format(port=6543))
    assert url.startswith("postgresql://")
    assert url.endswith("?sslmode=require")


def test_existing_sslmode_kept():
    url = normalize_database_url("postgresql://u:p@localhost:5432/db?sslmode=disable")
    assert "sslmode=disable" in url and "require" not in url


def test_sqlite_untouched():
    assert normalize_database_url("sqlite:///./green.db") == "sqlite:///./green.db"


def test_password_never_in_masked_url():
    masked = mask_database_url(normalize_database_url(POOLER.format(port=5432)))
    assert "s3cr3t-pw" not in masked and "***" in masked


def test_transaction_pooler_uses_nullpool():
    assert engine_kwargs(normalize_database_url(POOLER.format(port=6543)))["poolclass"] is NullPool


def test_session_pooler_uses_small_pool():
    kw = engine_kwargs(normalize_database_url(POOLER.format(port=5432)))
    assert "poolclass" not in kw
    assert kw["pool_size"] == 2 and kw["max_overflow"] == 2


def test_direct_connection_warns_ipv6():
    assert database_warnings("postgresql://u:p@db.abcd.supabase.co:5432/postgres")
    assert not database_warnings(normalize_database_url(POOLER.format(port=6543)))


def test_startup_log_hides_password():
    env = dict(os.environ, DATABASE_URL=POOLER.format(port=6543), SECRET_KEY="x", DEBUG="false")
    code = "import logging; logging.basicConfig(level=logging.INFO); import database"
    r = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(os.path.dirname(__file__)),
                       env=env, capture_output=True, text=True, timeout=60)
    assert "s3cr3t-pw" not in r.stdout + r.stderr
    assert "Database: postgresql://postgres.abcd:***@" in r.stderr
