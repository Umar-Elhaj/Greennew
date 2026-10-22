"""
Shared pytest fixtures.

The environment is configured BEFORE any backend module is imported:
config.py reads it at import time. Each test session gets its own
temporary SQLite database and MEDIA_DIR, so a developer's .env (which may
point at Supabase) is never used: real env vars win over .env.
"""

import io
import os
import sys
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="green-tests-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "test.db")
os.environ["MEDIA_DIR"] = os.path.join(_TMP, "media")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DEBUG"] = "false"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("WEATHER_API_KEY", None)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import rover_common  # noqa: E402
from database import Base, engine  # noqa: E402


FAKE_PREDICTION = {
    "class_raw":        "Corn_Leaf_Blight",
    "detected_disease": "Corn_Leaf_Blight",
    "disease_name":     "Corn Leaf Blight",
    "plant_type":       "Corn",
    "confidence":       0.91,
    "severity":         "high",
    "top3": [
        {"class": "Corn Leaf Blight", "confidence": 91.0},
        {"class": "Corn Brown Spots", "confidence": 5.0},
        {"class": "Corn Healthy",     "confidence": 2.0},
    ],
}


@pytest.fixture(autouse=True)
def _fresh_db():
    """Every test starts from an empty schema."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    # Not used as a context manager on purpose: the lifespan would start
    # the background warmup thread that loads the real model.
    return TestClient(main.app)


@pytest.fixture
def fake_model(monkeypatch):
    """Replace the EfficientNet forward pass with a fixed prediction."""
    calls = []

    def _predict(image_bytes):
        calls.append(len(image_bytes))
        return dict(FAKE_PREDICTION)

    monkeypatch.setattr(rover_common, "predict", _predict)
    return calls


def jpeg_bytes(color=(40, 160, 60), size=(64, 48)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


_counter = {"n": 0}


def register(client, **overrides) -> dict:
    """Create a user and return {"token", "user", "headers"}."""
    _counter["n"] += 1
    payload = {
        "first_name": "Test",
        "last_name":  "User",
        "phone":      f"+2376900{_counter['n']:05d}",
        "password":   "secret123",
    }
    payload.update(overrides)
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "token":   data["access_token"],
        "user":    data["user"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


@pytest.fixture
def user(client):
    return register(client)


@pytest.fixture
def other_user(client):
    return register(client)
