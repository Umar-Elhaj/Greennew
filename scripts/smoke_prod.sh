#!/usr/bin/env bash
# ============================================================
# GREEN — production smoke test
#
# Usage:
#   SMOKE_IDENTIFIER=... SMOKE_PASSWORD=... scripts/smoke_prod.sh https://green.example.org [image.jpg]
#
# Credentials of a dedicated test account come from the environment and
# are never printed. The test image defaults to a generated 64x48 JPEG.
# Checks: health, login, parcels list, analysis of one image, read-back of
# the stored image (authenticated, and refused without token), one
# GREEN Data endpoint (only if the account has the partner/admin role).
# Exit code = number of failed checks.
# ============================================================
set -u

BASE="${1:?usage: $0 <base_url> [image.jpg]}"
BASE="${BASE%/}"
IMAGE="${2:-}"
: "${SMOKE_IDENTIFIER:?set SMOKE_IDENTIFIER (test account phone or email)}"
: "${SMOKE_PASSWORD:?set SMOKE_PASSWORD}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILS=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILS=$((FAILS + 1)); }
json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$3" 2>/dev/null; }

echo "GREEN smoke test → $BASE"

# 1. health
code=$(curl -s -o "$TMP/health.json" -w '%{http_code}' "$BASE/api/health")
[ "$code" = 200 ] && [ "$(json x "d['status']" "$TMP/health.json")" = ok ] \
  && pass "GET /api/health" || fail "GET /api/health (HTTP $code)"

# 2. login (credentials sent in the body via a file, never on the command line)
python3 - "$TMP/login.json" <<'PY'
import json, os, sys
json.dump({"identifier": os.environ["SMOKE_IDENTIFIER"], "password": os.environ["SMOKE_PASSWORD"]},
          open(sys.argv[1], "w"))
PY
code=$(curl -s -o "$TMP/token.json" -w '%{http_code}' -H 'Content-Type: application/json' \
  --data @"$TMP/login.json" "$BASE/api/auth/login")
rm -f "$TMP/login.json"
TOKEN="$(json x "d['access_token']" "$TMP/token.json")"
if [ "$code" = 200 ] && [ -n "$TOKEN" ]; then pass "POST /api/auth/login"; else
  fail "POST /api/auth/login (HTTP $code)"; echo "  cannot continue without a token"; exit "$FAILS"; fi
AUTH=(-H "Authorization: Bearer $TOKEN")

# 3. parcels
code=$(curl -s -o "$TMP/parcels.json" -w '%{http_code}' "${AUTH[@]}" "$BASE/api/parcels")
[ "$code" = 200 ] && pass "GET /api/parcels ($(json x "len(d)" "$TMP/parcels.json") parcels)" \
  || fail "GET /api/parcels (HTTP $code)"

# 4. analysis of one image
if [ -z "$IMAGE" ]; then
  IMAGE="$TMP/leaf.jpg"
  python3 -c "from PIL import Image; Image.new('RGB',(64,48),(40,160,60)).save('$IMAGE')" 2>/dev/null \
    || printf '\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9' > "$IMAGE"
fi
start=$(date +%s.%N)
code=$(curl -s -o "$TMP/analysis.json" -w '%{http_code}' "${AUTH[@]}" \
  -F "file=@$IMAGE;type=image/jpeg" "$BASE/api/camera/upload")
secs=$(python3 -c "print(round($(date +%s.%N) - $start, 2))")
if [ "$code" = 200 ]; then
  pass "POST /api/camera/upload → $(json x "d['disease']['disease_name']" "$TMP/analysis.json") (${secs}s)"
else
  fail "POST /api/camera/upload (HTTP $code, ${secs}s): $(head -c 200 "$TMP/analysis.json")"
fi

# 5. stored image: readable with token, refused without
IMG_URL="$(json x "d.get('image_path') or ''" "$TMP/analysis.json")"
if [ -n "$IMG_URL" ]; then
  code=$(curl -s -o "$TMP/img" -w '%{http_code}' "${AUTH[@]}" "$BASE$IMG_URL")
  ctype=$(file -b --mime-type "$TMP/img" 2>/dev/null || echo "?")
  [ "$code" = 200 ] && pass "GET stored image with token ($ctype)" || fail "GET stored image with token (HTTP $code)"
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$IMG_URL")
  [ "$code" = 401 ] && pass "GET stored image without token → 401" || fail "GET stored image without token (HTTP $code, expected 401)"
else
  fail "stored image path missing from the analysis response"
fi

# 6. GREEN Data (partner/admin only)
code=$(curl -s -o "$TMP/gd.json" -w '%{http_code}' "${AUTH[@]}" "$BASE/api/green-data/overview")
case "$code" in
  200) pass "GET /api/green-data/overview" ;;
  403) pass "GET /api/green-data/overview → 403 (test account is not partner/admin)" ;;
  *)   fail "GET /api/green-data/overview (HTTP $code)" ;;
esac

echo
[ "$FAILS" -eq 0 ] && echo "All checks passed." || echo "$FAILS check(s) failed."
exit "$FAILS"
