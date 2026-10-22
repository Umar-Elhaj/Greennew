#!/usr/bin/env python3
"""
GREEN — media storage report.

Prints disk usage and file count of MEDIA_DIR, then the inconsistencies:
  - orphan files: on disk, but no disease_analyses row points to them;
  - missing files: a row points to an image that is not on disk.
Nothing is deleted unless --apply is given, and then only orphan FILES
(database rows are never modified by this script).

Usage (from the repository root, with the production environment loaded):
  .venv/bin/python scripts/media_report.py            # report only
  .venv/bin/python scripts/media_report.py --apply    # also delete orphan files
"""

import argparse
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)
os.environ.setdefault("DEBUG", "true")  # no SECRET_KEY needed to read the DB

import logging  # noqa: E402

logging.disable(logging.CRITICAL)

from database import SessionLocal  # noqa: E402
from media import MEDIA_DIR, MEDIA_PATH_RE, thumb_path  # noqa: E402
from models import DiseaseAnalysis  # noqa: E402


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def scan():
    files, total = {}, 0
    for root, _, names in os.walk(MEDIA_DIR):
        for name in names:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, MEDIA_DIR).replace(os.sep, "/")
            size = os.path.getsize(full)
            files[rel] = size
            total += size
    return files, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="delete orphan files")
    args = ap.parse_args()

    files, total = scan()
    db = SessionLocal()
    try:
        rows = [p for (p,) in db.query(DiseaseAnalysis.image_path).filter(DiseaseAnalysis.image_path.isnot(None))]
    finally:
        db.close()

    expected = set()
    for p in rows:
        expected.add(p)
        expected.add(thumb_path(p) if MEDIA_PATH_RE.match(p) else p)

    orphans = sorted(f for f in files if f not in expected)
    missing = sorted(p for p in rows if p not in files)
    no_thumb = sum(1 for p in rows if MEDIA_PATH_RE.match(p) and p in files and thumb_path(p) not in files)
    orphan_bytes = sum(files[f] for f in orphans)

    print(f"MEDIA_DIR      : {MEDIA_DIR}")
    print(f"disk used      : {human(total)} in {len(files)} files")
    print(f"analysis rows  : {len(rows)} with an image ({no_thumb} without thumbnail)")
    print(f"orphan files   : {len(orphans)} ({human(orphan_bytes)})")
    for f in orphans[:20]:
        print(f"  - {f}")
    if len(orphans) > 20:
        print(f"  … {len(orphans) - 20} more")
    print(f"missing files  : {len(missing)} (rows whose image is not on disk)")
    for p in missing[:20]:
        print(f"  - {p}")

    if args.apply and orphans:
        deleted = 0
        for f in orphans:
            try:
                os.remove(os.path.join(MEDIA_DIR, f))
                deleted += 1
            except OSError as e:
                print(f"  cannot delete {f}: {e.strerror}")
        print(f"deleted        : {deleted} orphan files ({human(orphan_bytes)})")
    elif orphans:
        print("(dry run: re-run with --apply to delete the orphan files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
