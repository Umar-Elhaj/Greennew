#!/usr/bin/env python3
"""
GREEN — give a role to an account (administrator tool, run on the server).

Roles: farmer (default) | agronomist (verifies analyses, sees their images)
       | partner (GREEN Data) | admin (everything).

Usage (from the repository root, with the server's environment loaded):
  .venv/bin/python scripts/set_role.py --phone +237690000000 --role partner
  .venv/bin/python scripts/set_role.py --email someone@example.org --role admin
  .venv/bin/python scripts/set_role.py --list            # accounts that are not farmers
The account is identified by phone or email; nothing else is changed.
"""

import argparse
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)
os.environ.setdefault("DEBUG", "true")   # no SECRET_KEY needed for this tool

# DEBUG is forced above only to skip SECRET_KEY: without an explicit
# DATABASE_URL the tool would silently work on a local SQLite file.
if not os.environ.get("DATABASE_URL", "").strip():
    print("DATABASE_URL is not set: load the server environment first "
          "(GUIDE_INTEGRATION_O2SWITCH.md, step 10).", file=sys.stderr)
    sys.exit(2)

import logging  # noqa: E402

logging.disable(logging.CRITICAL)

ROLES = ("farmer", "agronomist", "partner", "admin")


def main() -> int:
    ap = argparse.ArgumentParser()
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--phone")
    who.add_argument("--email")
    who.add_argument("--list", action="store_true")
    ap.add_argument("--role", choices=ROLES)
    args = ap.parse_args()

    from database import SessionLocal
    from models import User

    db = SessionLocal()
    try:
        if args.list:
            for u in db.query(User).filter(User.role != "farmer").order_by(User.role, User.id).all():
                print(f"{u.id:>6}  {u.role:<11} {u.first_name} {u.last_name}")
            return 0
        if not args.role:
            ap.error("--role is required")
        q = db.query(User)
        if args.phone:
            phone = args.phone.replace(" ", "").replace("-", "")
            user = q.filter(User.phone == phone).first()
        else:
            user = q.filter(User.email == args.email.strip().lower()).first()
        if user is None:
            print("No account with this phone/email.")
            return 1
        previous = user.role
        user.role = args.role
        db.commit()
        print(f"account {user.id}: {previous} -> {args.role}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
