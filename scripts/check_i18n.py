#!/usr/bin/env python3
"""
GREEN — i18n consistency checker.

Fails (exit 1) when:
  1. the key sets of `en` and `fr` differ;
  2. a translation value is empty;
  3. a visible HTML text node (or a placeholder/title/aria-label/alt
     attribute) is not carried by a data-i18n* attribute, unless it is in
     the explicit exception list (scripts/i18n_exceptions.txt) or contains
     no letters at all (numbers, symbols, units like "ha");
  4. a key used in HTML (data-i18n*) or JS (I18n.t('…') / t('…')) does not
     exist in the dictionary. A key `x` used with plural forms is satisfied
     by `x_one` + `x_other`;
  5. frontend/js/translations.js is not up to date with frontend/i18n/*.json.

Usage:
  python scripts/check_i18n.py            # check, exit 1 on failure
  python scripts/check_i18n.py --summary  # one line per file only
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_i18n  # noqa: E402
EXCEPTIONS_PATH = Path(__file__).resolve().parent / "i18n_exceptions.txt"

LANGS = ("en", "fr")
SKIP_CONTENT_TAGS = {"script", "style", "svg", "noscript", "template", "code", "pre"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
             "meta", "param", "source", "track", "wbr"}
TEXT_ATTRS = {
    "placeholder": "data-i18n-placeholder",
    "title":       "data-i18n-title",
    "aria-label":  "data-i18n-aria-label",
    "alt":         "data-i18n-alt",
}
KEY_ATTRS = ("data-i18n", "data-i18n-html", *TEXT_ATTRS.values())
HAS_LETTER = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
JS_KEY_RE = re.compile(r"""(?<![\w$])(?:[Ii]18n\.)?t\(\s*['"]([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)['"]""")


def flatten(obj, prefix=""):
    for k, v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from flatten(v, key + ".")
        else:
            yield key, v


def load_exceptions() -> set:
    if not EXCEPTIONS_PATH.exists():
        return set()
    out = set()
    for line in EXCEPTIONS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out


class PageScanner(HTMLParser):
    """Collects untranslated visible text and the i18n keys referenced."""

    def __init__(self, exceptions):
        super().__init__(convert_charrefs=True)
        self.exceptions = exceptions
        self.stack = []          # [(tag, covers_text, skip_content)]
        self.untranslated = []   # [(line, text)]
        self.keys = []           # [(line, key)]
        self.scripts = []        # inline script bodies

    # -- helpers -----------------------------------------------------------
    def _skipping(self):
        return any(skip for _, _, skip in self.stack)

    def _covered(self):
        # data-i18n covers the element's own text; data-i18n-html covers descendants too
        if self.stack and self.stack[-1][1]:
            return True
        return any(c == "html" for _, c, _ in self.stack)

    def _is_exempt(self, text):
        return not HAS_LETTER.search(text) or text in self.exceptions

    # -- parser callbacks --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        line = self.getpos()[0]
        for attr in KEY_ATTRS:
            if a.get(attr):
                self.keys.append((line, a[attr]))
        if not self._skipping():
            for attr, i18n_attr in TEXT_ATTRS.items():
                val = (a.get(attr) or "").strip()
                if val and i18n_attr not in a and not self._is_exempt(val):
                    self.untranslated.append((line, f'[{attr}] {val}'))
        if tag in VOID_TAGS:
            return
        covers = "html" if "data-i18n-html" in a else bool("data-i18n" in a)
        self.stack.append((tag, covers, tag in SKIP_CONTENT_TAGS))
        self._in_script = tag == "script" and "src" not in a

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] == "script":
            self.scripts.append((self.getpos()[0], data))
            return
        text = " ".join(data.split())
        if not text or self._skipping() or self._covered() or self._is_exempt(text):
            return
        if self.stack and self.stack[-1][0] in ("title",):
            # <title> must be translated too; it is visible in the tab
            pass
        self.untranslated.append((self.getpos()[0], text))


def js_keys(source: str, base_line: int = 1):
    for m in JS_KEY_RE.finditer(source):
        yield base_line + source.count("\n", 0, m.start()), m.group(1)


def key_exists(key: str, keys: set) -> bool:
    return key in keys or (f"{key}_one" in keys and f"{key}_other" in keys)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true", help="print one line per file")
    args = ap.parse_args()

    errors = []
    current = build_i18n.OUT.read_text(encoding="utf-8") if build_i18n.OUT.exists() else ""
    if build_i18n.render() != current:
        errors.append("[build] frontend/js/translations.js is out of date: run scripts/build_i18n.py")
    data = build_i18n.merged()
    flat = {lang: dict(flatten(data.get(lang, {}))) for lang in LANGS}

    # 1. same key sets
    en, fr = set(flat["en"]), set(flat["fr"])
    for k in sorted(en - fr):
        errors.append(f"[keys] missing in fr: {k}")
    for k in sorted(fr - en):
        errors.append(f"[keys] missing in en: {k}")

    # 2. empty values
    for lang in LANGS:
        for k, v in flat[lang].items():
            if not isinstance(v, str) or not v.strip():
                errors.append(f"[empty] {lang}.{k}")

    known = en & fr
    exceptions = load_exceptions()
    per_file = {}

    # 3 + 4. HTML pages
    for page in sorted(FRONTEND.glob("*.html")):
        scanner = PageScanner(exceptions)
        scanner.feed(page.read_text(encoding="utf-8"))
        rel = page.relative_to(ROOT)
        missing = [(ln, k) for ln, k in scanner.keys if not key_exists(k, known)]
        for base, body in scanner.scripts:
            missing += [(ln, k) for ln, k in js_keys(body, base) if not key_exists(k, known)]
        per_file[str(rel)] = (len(scanner.untranslated), len(missing))
        for ln, text in scanner.untranslated:
            errors.append(f"[untranslated] {rel}:{ln}: {text[:90]}")
        for ln, k in missing:
            errors.append(f"[unknown-key] {rel}:{ln}: {k}")

    # 4. JS files
    for js in sorted(p for p in (FRONTEND / "js").glob("*.js") if p.name != "translations.js"):
        rel = js.relative_to(ROOT)
        missing = [(ln, k) for ln, k in js_keys(js.read_text(encoding="utf-8")) if not key_exists(k, known)]
        per_file[str(rel)] = (0, len(missing))
        for ln, k in missing:
            errors.append(f"[unknown-key] {rel}:{ln}: {k}")

    if args.summary:
        for f, (u, m) in per_file.items():
            print(f"{f:32s} untranslated={u:4d} unknown_keys={m}")
    else:
        for e in errors:
            print(e)

    print(f"\ncheck_i18n: {len(known)} keys/lang, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
