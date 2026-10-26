#!/usr/bin/env python3
"""
GREEN — database check (read-only).

Connects with DATABASE_URL and prints: server version, pool mode, current
and expected Alembic revision, row count per table. The URL (host, user,
password) is never printed.

Usage (from the repository root):
  .venv/bin/python scripts/db_check.py
Exit code: 0 = reachable and schema up to date, 1 = schema behind, 2 = unreachable.
"""

import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)
os.environ.setdefault("DEBUG", "true")  # db_check never needs SECRET_KEY

# DEBUG is forced above only to skip SECRET_KEY: without an explicit
# DATABASE_URL the tool would silently work on a local SQLite file.
if not os.environ.get("DATABASE_URL", "").strip():
    print("DATABASE_URL is not set: load the server environment first "
          "(GUIDE_INTEGRATION_O2SWITCH.md, step 12).", file=sys.stderr)
    sys.exit(2)

import logging  # noqa: E402

logging.disable(logging.CRITICAL)  # database.py logs the masked URL; stay silent

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from database import engine  # noqa: E402
from schema_check import current_revision, head_revision  # noqa: E402


def main() -> int:
    dialect = engine.dialect.name
    pool = "NullPool (transaction pooler)" if isinstance(engine.pool, NullPool) else type(engine.pool).__name__
    print(f"backend : {dialect} — pool {pool}")
    try:
        with engine.connect() as conn:
            if dialect == "postgresql":
                version = conn.execute(text("show server_version")).scalar()
            elif dialect == "mysql":
                version = conn.execute(text("select version()")).scalar()   # e.g. 10.6.x-MariaDB
            else:
                version = conn.execute(text("select sqlite_version()")).scalar()
            print(f"version : {version}")

            current, head = current_revision(conn), head_revision()
            print(f"alembic : current={current} head={head}")

            tables = sorted(t for t in inspect(conn).get_table_names() if t != "alembic_version")
            print("rows    :")
            for t in tables:
                quoted = conn.dialect.identifier_preparer.quote(t)   # "t" or `t` (MySQL)
                n = conn.execute(text(f"select count(*) from {quoted}")).scalar()  # noqa: S608 (names from the catalog)
                print(f"  {t:<20} {n}")
    except Exception as e:
        # The exception text can contain the host: print the type only.
        print(f"ERROR   : cannot reach the database ({type(e).__name__})")
        return 2

    if current != head:
        hint = "alembic stamp 0001_baseline, then " if current is None and tables else ""
        print(f"schema behind: run `{hint}alembic upgrade head` from backend/")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
