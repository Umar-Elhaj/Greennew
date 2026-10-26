"""
scripts/copy_database.py: former database (here SQLite at the pre-Alembic
baseline, standing in for Supabase) → new database at head (SQLite, or the
MySQL server of TEST_MYSQL_URL).
"""

import os
import subprocess
import sys

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from test_migrations import _alembic

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "copy_database.py")


def _source(tmp_path) -> str:
    url = "sqlite:///" + str(tmp_path / "source.db")
    command.upgrade(_alembic(url), "0001_baseline")
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("insert into users (id, first_name, last_name, phone, password_hash, created_at, updated_at) "
                       "values (7, 'Awa', 'Éto''o', '+237690000001', 'x', '2026-10-01 10:00:00', "
                       "'2026-10-01 10:00:00')"))
        c.execute(text("insert into parcels (id, user_id, name, geometry, latitude, created_at, updated_at) "
                       "values (3, 7, 'Parcelle 🌽', '{\"type\": \"Polygon\"}', 3.8667123, "
                       "'2026-10-01 10:00:00', '2026-10-01 10:00:00')"))
        c.execute(text("insert into disease_analyses (id, user_id, parcel_id, confidence, consent_dataset, created_at) "
                       "values (11, 7, 3, 0.9, 1, '2026-10-01 10:00:00.123456')"))
    eng.dispose()
    return url


def _run(source: str, target: str, *args):
    env = dict(os.environ, SOURCE_DATABASE_URL=source, DATABASE_URL=target)
    return subprocess.run([sys.executable, SCRIPT, *args], env=env, capture_output=True, text=True, timeout=120)


def _check_copy(source: str, target: str):
    command.upgrade(_alembic(target), "head")

    dry = _run(source, target)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "default value for: location_consent, role" in dry.stdout
    assert "missions" in dry.stdout and "absent from the source" in dry.stdout

    done = _run(source, target, "--apply")
    assert done.returncode == 0, done.stdout + done.stderr

    eng = create_engine(target)
    with eng.connect() as c:
        user = c.execute(text("select id, last_name, role, location_consent from users")).one()
        parcel = c.execute(text("select id, user_id, name, latitude from parcels")).one()
        created = c.execute(text("select created_at from disease_analyses where id = 11")).scalar()
    assert tuple(user) == (7, "Éto'o", "farmer", 0)
    assert tuple(parcel) == (3, 7, "Parcelle 🌽", 3.8667123)
    assert str(created).endswith(".123456")
    eng.dispose()

    again = _run(source, target, "--apply")
    assert again.returncode == 1 and "target not empty" in again.stdout


def test_copy_into_sqlite(tmp_path):
    _check_copy(_source(tmp_path), "sqlite:///" + str(tmp_path / "target.db"))


@pytest.mark.mysql
def test_copy_into_mysql(tmp_path, mysql_url):
    _check_copy(_source(tmp_path), mysql_url)


def test_copy_refuses_target_behind(tmp_path):
    target = "sqlite:///" + str(tmp_path / "target.db")
    command.upgrade(_alembic(target), "0003_map_missions")
    r = _run(_source(tmp_path), target, "--apply")
    assert r.returncode == 1 and "run `alembic upgrade head`" in r.stdout


def test_secrets_never_printed(tmp_path):
    r = _run("postgresql://u:s3cr3t-pw@127.0.0.1:1/db", "sqlite:///" + str(tmp_path / "t.db"))
    assert "s3cr3t-pw" not in r.stdout + r.stderr
