#!/usr/bin/env python3
"""
GREEN — one-time copy of the data of the former database (Supabase
PostgreSQL) into the MySQL/MariaDB database of o2switch.

  source : SOURCE_DATABASE_URL (read-only: only SELECT statements)
  target : DATABASE_URL, already created by `alembic upgrade head` and EMPTY

Both URLs come from the environment, never from the command line (shell
history, process list) and are never printed.

Usage (from the repository root):
  scripts/copy_database.py            # dry run: what would be copied
  scripts/copy_database.py --apply    # copy, in a single transaction

Rows keep their ids, so links between tables, image paths and signed URLs
stay valid; AUTO_INCREMENT continues after the highest copied id. Columns
that the source does not have yet (a database still at the pre-Alembic
baseline) take their default value (role = farmer, consents = false…).
A failure rolls the whole copy back: the target stays empty.

Needs both drivers in the same environment: PyMySQL (requirements-prod)
and psycopg2-binary (`pip install psycopg2-binary`, for this copy only).
Exit code: 0 = done (or dry run OK), 1 = refused (see message), 2 = unreachable.
"""

import argparse
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)
os.environ.setdefault("DEBUG", "true")  # the copy never needs SECRET_KEY

if not os.environ.get("DATABASE_URL", "").strip() or not os.environ.get("SOURCE_DATABASE_URL", "").strip():
    print("DATABASE_URL (target, o2switch) and SOURCE_DATABASE_URL (former database) must both be set "
          "(GUIDE_INTEGRATION_O2SWITCH.md, steps 12 and 15).", file=sys.stderr)
    sys.exit(2)

import logging  # noqa: E402

logging.disable(logging.CRITICAL)  # database.py logs the masked URL; stay silent

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select  # noqa: E402

import models  # noqa: E402,F401  (registers every table on Base.metadata)
from database import Base, engine as target  # noqa: E402
from db_url import engine_kwargs, normalize_database_url  # noqa: E402
from schema_check import current_revision, head_revision  # noqa: E402

# Parents before children (foreign keys)
TABLES = ("users", "parcels", "missions", "disease_analyses", "chat_sessions", "chat_messages")
BATCH = 500


def _count(conn, table) -> int:
    return conn.execute(select(func.count()).select_from(table)).scalar()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="copy the rows (default: dry run)")
    args = parser.parse_args()

    source_url = normalize_database_url(os.environ["SOURCE_DATABASE_URL"])
    if source_url == target.url.render_as_string(hide_password=False):
        print("REFUSED : source and target are the same database.")
        return 1
    source = create_engine(source_url, **engine_kwargs(source_url))
    print(f"source  : {source.dialect.name}")
    print(f"target  : {target.dialect.name}")

    try:
        with source.connect() as src, target.connect() as tgt:
            current, head = current_revision(tgt), head_revision()
            if current != head:
                print(f"REFUSED : target schema at {current}, expected {head}: run `alembic upgrade head` "
                      "on the target first.")
                return 1
            busy = [t for t in TABLES if _count(tgt, Base.metadata.tables[t])]
            if busy:
                print(f"REFUSED : target not empty ({', '.join(busy)}): the copy only fills a new database.")
                return 1

            present = set(inspect(src).get_table_names())
            plan = []
            for name in TABLES:
                if name not in present:
                    print(f"  {name:<18} absent from the source: skipped")
                    continue
                src_table = Table(name, MetaData(), autoload_with=src)
                dst_table = Base.metadata.tables[name]
                columns = [c.name for c in dst_table.columns if c.name in src_table.c]
                defaulted = [c.name for c in dst_table.columns if c.name not in src_table.c]
                n = _count(src, src_table)
                plan.append((src_table, dst_table, columns, n))
                note = f" (default value for: {', '.join(defaulted)})" if defaulted else ""
                print(f"  {name:<18} {n:>7} row(s){note}")

            if not args.apply:
                print("dry run : nothing written. Re-run with --apply to copy.")
                return 0

            tgt.rollback()   # end the implicit transaction of the checks above
            with tgt.begin():
                for src_table, dst_table, columns, _ in plan:
                    last_id = None
                    while True:
                        q = select(*(src_table.c[c] for c in columns)).order_by(src_table.c.id).limit(BATCH)
                        if last_id is not None:
                            q = q.where(src_table.c.id > last_id)
                        rows = [dict(r._mapping) for r in src.execute(q)]
                        if not rows:
                            break
                        tgt.execute(dst_table.insert(), rows)
                        last_id = rows[-1]["id"]

            for _, dst_table, _, n in plan:
                copied = _count(tgt, dst_table)
                status = "ok" if copied == n else f"MISMATCH (source {n})"
                print(f"copied  : {dst_table.name:<18} {copied:>7} {status}")
                if copied != n:
                    return 1
    except Exception as e:
        # The exception text can contain the host: print the type and the
        # driver's error code only (e.g. 1062 = duplicate key on MySQL).
        code = getattr(getattr(e, "orig", None), "args", [None])[0]
        print(f"ERROR   : {type(e).__name__}{f' {code}' if isinstance(code, int) else ''} (nothing was copied)")
        return 2
    finally:
        source.dispose()
    print("done    : check the application, then keep the former database read-only as a backup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
