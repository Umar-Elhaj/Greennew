#!/usr/bin/env python3
"""
GREEN — write frontend/vercel.json for a frontend on Vercel and the API on o2switch.

Vercel serves the static pages; every /api/* request is rewritten (proxied)
to the API origin, so the browser stays on one origin: no CORS, the
Authorization header and signed image URLs work unchanged.

Usage:
  python scripts/configure_vercel.py https://api.example.cm      # write the rewrite
  python scripts/configure_vercel.py --check                     # show the current API origin
Then commit frontend/vercel.json and redeploy on Vercel.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

PATH = Path(__file__).resolve().parent.parent / "frontend" / "vercel.json"

SECURITY_HEADERS = [
    {"key": "X-Content-Type-Options", "value": "nosniff"},
    {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
    {"key": "X-Frame-Options", "value": "DENY"},
    {"key": "Permissions-Policy", "value": "camera=(self), geolocation=(self), microphone=()"},
    {"key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains"},
]


def build(api_origin):
    config = {
        "cleanUrls": True,
        "trailingSlash": False,
        "redirects": [
            {"source": "/drone", "destination": "/camera", "permanent": True},
            {"source": "/drone.html", "destination": "/camera", "permanent": True},
        ],
        "headers": [
            {"source": "/(.*)", "headers": SECURITY_HEADERS},
            # the dictionary changes with each release: always revalidate
            {"source": "/js/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]},
        ],
    }
    if api_origin:
        config["rewrites"] = [{"source": "/api/:path*", "destination": f"{api_origin}/api/:path*"}]
    return config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("api_origin", nargs="?", help="https://<o2switch API domain> (no path)")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        current = json.loads(PATH.read_text()) if PATH.exists() else {}
        rw = current.get("rewrites") or []
        print(rw[0]["destination"].replace("/api/:path*", "") if rw else "no API rewrite: /api/* is not proxied yet")
        return 0 if rw else 1
    origin = None
    if args.api_origin:
        u = urlparse(args.api_origin)
        if u.scheme != "https" or not u.netloc or u.path not in ("", "/"):
            print("The API origin must look like https://api.example.cm (HTTPS, no path).")
            return 2
        origin = f"https://{u.netloc}"
    PATH.write_text(json.dumps(build(origin), indent=2) + "\n")
    print(f"wrote {PATH.relative_to(PATH.parent.parent)}" + (f" (API: {origin})" if origin else " (no API rewrite)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
