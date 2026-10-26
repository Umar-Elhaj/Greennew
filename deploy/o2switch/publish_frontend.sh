#!/usr/bin/env bash
# ============================================================
# GREEN — publish the frontend in the document root of the o2switch domain
#
# Usage (on the server, after each `git pull`):
#   ~/green/deploy/o2switch/publish_frontend.sh /home/sc1jsgw2086/api-green.gitingeniering.com
#
# Each top-level entry of frontend/ (pages, css/, js/, vendor/, assets/) is
# linked into the document root. Apache then serves these files itself
# (with the cache rules of the .htaccess) and only /api/* and the clean
# page URLs (/dashboard, /map…) reach Passenger, which saves the Python
# processes counted by the LVE limits. Links, not copies: a `git pull` updates
# the site at once and nothing can go stale.
# If Apache did not serve them, FastAPI still serves the same files: the
# site works either way.
#
# Never touched: .htaccess (Passenger block written by cPanel),
# .well-known (Let's Encrypt) and any real file or folder already there.
# ============================================================
set -euo pipefail

DOCROOT="${1:?usage: $0 <document root of the domain>}"
DOCROOT="${DOCROOT%/}"
FRONT="$(cd "$(dirname "$0")/../../frontend" && pwd)"

[ -d "$DOCROOT" ] || { echo "no such directory: $DOCROOT" >&2; exit 1; }
case "$DOCROOT/" in
  "$FRONT"/*|"$(dirname "$FRONT")"/*) echo "the document root must be outside the repository" >&2; exit 1 ;;
esac
[ -f "$DOCROOT/.htaccess" ] || echo "warning: no .htaccess yet (create the Python application first, step 12)"

linked=0
for entry in "$FRONT"/*; do
  name="$(basename "$entry")"
  case "$name" in
    vercel.json|i18n) continue ;;     # Vercel config; i18n sources (built into js/translations.js)
  esac
  target="$DOCROOT/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "skipped: $target is a real file or folder (move it away to publish $name)"
    continue
  fi
  ln -sfn "$entry" "$target"
  linked=$((linked + 1))
done

# Links whose target left the repository (page removed, folder renamed)
find "$DOCROOT" -maxdepth 1 -type l ! -exec test -e {} \; -print -delete | sed 's/^/removed dangling link: /'

echo "frontend published: $linked entries linked into $DOCROOT"
