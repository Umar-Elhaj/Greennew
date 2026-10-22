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


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "geolocation=(self)" in r.headers["permissions-policy"]


def test_passenger_entry_point_serves_requests():
    """passenger_wsgi.application is a WSGI callable wrapping the FastAPI app."""
    import io
    import sys

    import passenger_wsgi

    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/health", "QUERY_STRING": "", "SERVER_NAME": "test",
               "SERVER_PORT": "80", "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.url_scheme": "http",
               "wsgi.input": io.BytesIO(b""), "wsgi.errors": sys.stderr, "wsgi.version": (1, 0),
               "wsgi.multithread": True, "wsgi.multiprocess": True, "wsgi.run_once": False}
    status = {}
    body = b"".join(passenger_wsgi.application(environ, lambda s, h, *a: status.update(s=s, h=h)))
    assert status["s"].startswith("200") and b'"status":"ok"' in body
