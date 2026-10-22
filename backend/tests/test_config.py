"""Startup guards of config.py, checked in a subprocess (config reads env at import)."""

import os
import subprocess
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _import_config(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DEBUG", "CORS_ORIGINS")}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import config; print(config.DEBUG, config.CORS_ORIGINS)"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )


def test_missing_secret_key_fails_in_production():
    r = _import_config({})
    assert r.returncode != 0
    assert "SECRET_KEY is not set" in r.stderr


def test_debug_is_false_by_default():
    r = _import_config({"SECRET_KEY": "x"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split()[0] == "False"


def test_dev_key_only_with_debug():
    r = _import_config({"DEBUG": "true"})
    assert r.returncode == 0, r.stderr


def test_cors_origins_parsed_and_empty_by_default():
    assert "[]" in _import_config({"SECRET_KEY": "x"}).stdout
    r = _import_config({"SECRET_KEY": "x", "CORS_ORIGINS": "https://a.example, https://b.example ,"})
    assert "['https://a.example', 'https://b.example']" in r.stdout


def test_no_wildcard_cors_with_credentials():
    import main
    from fastapi.middleware.cors import CORSMiddleware

    for m in main.app.user_middleware:
        if m.cls is CORSMiddleware:
            assert not (m.kwargs.get("allow_credentials") and "*" in m.kwargs.get("allow_origins", []))
