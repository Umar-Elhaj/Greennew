"""
Shared pytest fixtures.

The environment is configured BEFORE any backend module is imported:
config.py reads it at import time. Each test session gets its own
temporary SQLite database and MEDIA_DIR, so a developer's .env (which may
point at a real database) is never used: real env vars win over .env.
"""

import io
import os
import shutil
import sys
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="green-tests-")
# TEST_DATABASE_URL runs the whole suite on a disposable MySQL/MariaDB or
# PostgreSQL (its tables are dropped between tests): never point it at real data.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or "sqlite:///" + os.path.join(_TMP, "test.db")
os.environ["MEDIA_DIR"] = os.path.join(_TMP, "media")
os.environ["PREDICTION_LOG_PATH"] = os.path.join(_TMP, "predictions.jsonl")
os.environ.pop("CONFIDENCE_THRESHOLD", None)   # the configured default (0.70) is tested
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
from routers import green_data_router  # noqa: E402
from database import Base, engine  # noqa: E402


def fake_probs(label="Corn leaf blight", p=0.91):
    """9 probabilities summing to 1, `label` getting `p` (labels.txt order)."""
    import numpy as np

    import inference

    probs = np.full(len(inference.LABELS), (1.0 - p) / (len(inference.LABELS) - 1), dtype=np.float32)
    probs[inference.LABELS.index(label)] = p
    return probs


def ok_result(code="Corn_Leaf_Blight", confidence=0.91, severity="high", plant="Corn") -> dict:
    """A stored-shape "ok" result for tests that only need an analysis row (any class code)."""
    import inference

    healthy = code in ("healthy", f"{plant}_Healthy")
    return {
        "status": "ok", "disease": code.replace("_", " "), "confidence": confidence, "chosen_crop": None,
        "model_version": inference.MODEL_VERSION, "threshold": inference.CONFIDENCE_THRESHOLD,
        "best": code.replace("_", " "), "probabilities": {},
        "class_raw": f"{plant}_Healthy" if healthy else code, "detected_disease": "healthy" if healthy else code,
        "disease_name": code, "plant_type": plant, "severity": severity, "top3": [],
    }


@pytest.fixture(autouse=True)
def _fresh_db():
    """Every test starts from an empty schema and an empty MEDIA_DIR."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    green_data_router.clear_cache()
    shutil.rmtree(os.environ["MEDIA_DIR"], ignore_errors=True)
    os.makedirs(os.environ["MEDIA_DIR"], exist_ok=True)
    yield


@pytest.fixture
def mysql_url():
    """A new, empty database on the disposable server of TEST_MYSQL_URL, dropped afterwards."""
    import uuid

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from db_url import normalize_database_url

    base = os.environ.get("TEST_MYSQL_URL")
    if not base:
        pytest.skip("TEST_MYSQL_URL not set")
    base = normalize_database_url(base)
    admin = create_engine(base)
    name = "green_mig_" + uuid.uuid4().hex[:8]
    with admin.connect() as c:
        c.execute(text(f"create database `{name}` character set utf8mb4 collate utf8mb4_unicode_ci"))
    yield make_url(base).set(database=name).render_as_string(hide_password=False)
    with admin.connect() as c:
        c.execute(text(f"drop database `{name}`"))
    admin.dispose()


@pytest.fixture
def client():
    # Not used as a context manager on purpose: the lifespan would start
    # the background warmup thread that loads the real model.
    return TestClient(main.app)


class FakeModel(list):
    """Calls made to the model (len = number of inferences); `probs` = next output."""
    probs = None
    crops: list


@pytest.fixture
def fake_model(monkeypatch):
    """
    Replace the classifier's forward pass with fixed probabilities (Corn leaf
    blight 0.91 by default); the real decision rule still runs on them.
    """
    import inference

    calls = FakeModel()
    calls.probs = fake_probs()
    calls.crops = []

    def _predict(image_bytes, chosen_crop=None):
        calls.append(len(image_bytes))
        calls.crops.append(chosen_crop)
        return inference.build_result(calls.probs, chosen_crop)

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
