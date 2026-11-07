"""
Disease classifier: preprocessing, decision rule, API statuses and prediction log.
The tests marked slow run the real TFLite model (they need ai-edge-litert or
tensorflow): pytest -m slow tests/test_inference.py
"""

import io
import json
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

import inference
from conftest import fake_probs, jpeg_bytes

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT = os.path.dirname(BACKEND)


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---- Labels -------------------------------------------------
def test_labels_are_the_9_classes_of_the_model_spec():
    spec = json.load(open(os.path.join(ROOT, "Models", "model_spec.json"), encoding="utf-8"))
    assert inference.LABELS == spec["classes"]
    assert len(inference.LABELS) == 9
    assert [inference.crop_of(label) for label in inference.LABELS] == ["Cassava"] * 3 + ["Corn"] * 3 + ["Tomato"] * 3
    assert spec["input_shape"] == [1, inference.INPUT_SIZE, inference.INPUT_SIZE, 3]
    assert inference.CLASS_CODES[5] == "Corn_Leaf_Blight" and inference.CLASS_CODES[8] == "Tomato_Healthy"


# ---- Preprocessing ------------------------------------------
def test_preprocess_shape_dtype_and_raw_pixel_range():
    x = inference.preprocess(png_bytes(Image.new("RGB", (300, 200), (255, 255, 255))))
    assert x.shape == (1, 224, 224, 3) and x.dtype == np.float32
    assert np.allclose(x, 255.0)       # 0–255, not normalized
    x = inference.preprocess(png_bytes(Image.new("RGB", (50, 80), (0, 0, 0))))
    assert np.allclose(x, 0.0)


def test_preprocess_is_rgb_and_drops_alpha():
    x = inference.preprocess(png_bytes(Image.new("RGB", (64, 64), (255, 0, 0))))
    assert np.allclose(x[0, :, :, 0], 255) and np.allclose(x[0, :, :, 1:], 0)      # red stays channel 0
    rgba = Image.new("RGBA", (64, 64), (10, 200, 30, 0))                            # fully transparent
    x = inference.preprocess(png_bytes(rgba))
    assert np.allclose(x[0, 0, 0], [10, 200, 30])                                   # alpha dropped, not composited


def test_preprocess_stretches_without_cropping():
    """A 3:1 image with red | green | blue thirds keeps all three thirds (no center crop)."""
    img = Image.new("RGB", (672, 224))
    for i, c in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        img.paste(c, (i * 224, 0, (i + 1) * 224, 224))
    x = inference.preprocess(png_bytes(img))[0]
    assert np.allclose(x[112, 10], [255, 0, 0])
    assert np.allclose(x[112, 112], [0, 255, 0])
    assert np.allclose(x[112, 213], [0, 0, 255])


def test_preprocess_downscale_is_antialiased():
    """A 1-pixel checkerboard reduced 3x averages to grey instead of aliasing."""
    board = ((np.indices((672, 672)).sum(axis=0) % 2) * 255).astype(np.uint8)
    x = inference.preprocess(png_bytes(Image.fromarray(board).convert("RGB")))
    assert abs(float(x.mean()) - 127.5) < 2 and float(x.std()) < 20


def test_preprocess_matches_tf_image_resize():
    """Reference of training: tf.image.resize(bilinear, antialias=True). Needs TensorFlow."""
    tf = pytest.importorskip("tensorflow")
    rng = np.random.default_rng(0)
    for size in [(640, 480), (150, 100), (1000, 333)]:
        arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
        ref = tf.image.resize(arr, (224, 224), method="bilinear", antialias=True).numpy()
        got = inference.preprocess(png_bytes(Image.fromarray(arr)))[0]
        assert float(np.abs(got - ref).max()) < 1.0, size


def test_preprocess_rejects_non_images():
    with pytest.raises(ValueError):
        inference.preprocess(b"not an image")


# ---- Decision rule ------------------------------------------
def _probs(**by_label):
    p = np.zeros(9, dtype=np.float32)
    for label, v in by_label.items():
        p[inference.LABELS.index(label.replace("_", " "))] = v
    return p


def test_threshold_is_the_configured_provisional_default():
    assert inference.CONFIDENCE_THRESHOLD == 0.70


def test_ok_unknown_and_wrong_crop():
    assert inference.decide(fake_probs("Cassava Mosaic", 0.93), "Cassava")[0] == "ok"
    assert inference.decide(fake_probs("Cassava Mosaic", 0.69), "Cassava")[0] == "unknown"
    assert inference.decide(fake_probs("Cassava Mosaic", 0.71), "Cassava")[0] == "ok"
    assert inference.decide(fake_probs("Cassava Mosaic", 0.93), "Tomato")[0] == "wrong_crop"
    # the crop check comes first, whatever the confidence
    assert inference.decide(fake_probs("Cassava Mosaic", 0.40), "Corn")[0] == "wrong_crop"


def test_without_chosen_crop_the_best_of_the_9_classes_is_used():
    assert inference.decide(fake_probs("Tomato blight leaf", 0.88), None)[:2] == ("ok", 7)
    assert inference.decide(fake_probs("Tomato blight leaf", 0.50), None)[0] == "unknown"


def test_never_renormalized_over_the_chosen_crop():
    # Renormalized over Cassava's 3 classes, Cassava Mosaic would get 0.5 / 0.65 = 0.77 and pass.
    probs = _probs(Cassava_Mosaic=0.50, Cassava_Healthy=0.15, Corn_Healthy=0.12, Tomato_healthy=0.12,
                   Corn_Yellowing=0.11)
    status, best, conf = inference.decide(probs, "Cassava")
    assert (status, inference.LABELS[best], round(conf, 2)) == ("unknown", "Cassava Mosaic", 0.50)


def test_maximum_is_never_taken_over_the_chosen_crop_only():
    # Masked to Cassava, the answer would be Cassava Healthy; the leaf is a tomato.
    probs = _probs(Tomato_blight_leaf=0.80, Cassava_Healthy=0.15, Cassava_Mosaic=0.05)
    status, best, _ = inference.decide(probs, "Cassava")
    assert status == "wrong_crop" and inference.LABELS[best] == "Tomato blight leaf"


def test_result_contract():
    r = inference.build_result(fake_probs("Corn leaf blight", 0.93), "Corn")
    assert {k: r[k] for k in ("status", "disease", "confidence", "chosen_crop", "model_version", "threshold")} == {
        "status": "ok", "disease": "Corn leaf blight", "confidence": 0.93, "chosen_crop": "Corn",
        "model_version": "classifier_v1", "threshold": 0.70}
    assert len(r["probabilities"]) == 9 and abs(sum(r["probabilities"].values()) - 1) < 1e-4
    assert r["detected_disease"] == "Corn_Leaf_Blight" and r["plant_type"] == "Corn" and len(r["top3"]) == 3
    for status, crop, p in [("unknown", "Corn", 0.5), ("wrong_crop", "Tomato", 0.93)]:
        r = inference.build_result(fake_probs("Corn leaf blight", p), crop)
        assert r["status"] == status and r["disease"] is None
    healthy = inference.build_result(fake_probs("Cassava Healthy", 0.9), "Cassava")
    assert healthy["detected_disease"] == "healthy" and healthy["severity"] == "none"


def test_threshold_and_model_version_come_from_the_environment():
    code = "import inference; print(inference.CONFIDENCE_THRESHOLD, inference.MODEL_VERSION)"
    env = dict(os.environ, CONFIDENCE_THRESHOLD="0.55", MODEL_VERSION="classifier_test", DEBUG="true")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["0.55", "classifier_test"]


# ---- API: crop, statuses, history and log -------------------
def _upload(client, headers, data=None, color=(40, 160, 60)):
    return client.post("/api/camera/upload", files={"file": ("leaf.jpg", jpeg_bytes(color=color), "image/jpeg")},
                       data=data or {}, headers=headers)


def _log_lines():
    path = inference.PREDICTION_LOG_PATH
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_invalid_crop_is_rejected_with_400(client, user, fake_model):
    for crop in ("Banana", "Groundnut"):
        r = _upload(client, user["headers"], {"crop": crop})
        assert r.status_code == 400, r.text
    assert fake_model == []


def test_crop_comes_from_the_request_then_the_parcel_else_all_crops(client, user, fake_model):
    h = user["headers"]
    maize = client.post("/api/parcels", json={"name": "Field", "crop_type": "Maize"}, headers=h).json()["id"]
    other = client.post("/api/parcels", json={"name": "Peanuts", "crop_type": "Groundnut"}, headers=h).json()["id"]
    assert _upload(client, h, {"crop": "corn"}, color=(10, 10, 10)).json()["chosen_crop"] == "Corn"
    assert _upload(client, h, {"parcel_id": maize}, color=(20, 20, 20)).json()["chosen_crop"] == "Corn"
    assert _upload(client, h, {"parcel_id": other}, color=(30, 30, 30)).json()["chosen_crop"] is None
    assert _upload(client, h, color=(40, 40, 40)).json()["chosen_crop"] is None
    assert fake_model.crops == ["Corn", "Corn", None, None]
    assert [e["crop_source"] for e in _log_lines()[-4:]] == ["request", "parcel", None, None]


def test_unknown_is_returned_logged_and_not_saved(client, user, fake_model):
    fake_model.probs = fake_probs("Corn leaf blight", 0.52)
    before = len(_log_lines())
    r = client.post("/api/camera/upload?lang=fr", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")},
                    data={"crop": "Corn"}, headers=user["headers"])
    body = r.json()
    assert r.status_code == 200
    assert (body["status"], body["disease"], body["confidence"], body["threshold"]) == ("unknown", None, 0.52, 0.70)
    assert body["analysis_id"] is None and body["fiche_terrain"] is None and body["image_path"] is None
    assert body["message"].startswith("Image non reconnue")
    assert client.get("/api/analysis/history", headers=user["headers"]).json()["total"] == 0
    assert not any(files for _, _, files in os.walk(os.environ["MEDIA_DIR"]))     # image not stored

    lines = _log_lines()
    assert len(lines) == before + 1
    entry = lines[-1]
    assert entry["status"] == "unknown" and entry["chosen_crop"] == "Corn" and entry["timestamp"]
    assert entry["model_version"] == "classifier_v1" and entry["threshold"] == 0.70
    assert list(entry["probabilities"]) == inference.LABELS


def test_wrong_crop_message_names_the_chosen_crop(client, user, fake_model):
    r = _upload(client, user["headers"], {"crop": "Tomato"}).json()
    assert r["status"] == "wrong_crop" and r["disease"] is None and r["chosen_crop"] == "Tomato"
    assert "tomato" in r["message"]
    assert client.get("/api/analysis/history", headers=user["headers"]).json()["total"] == 0


def test_ok_is_saved_with_the_model_version(client, user, fake_model):
    r = _upload(client, user["headers"], {"crop": "Corn"}).json()
    assert r["status"] == "ok" and r["disease"] == "Corn leaf blight" and r["analysis_id"]
    assert r["message"] is None and r["fiche_terrain"]["winner"]["code"] == "Corn_Leaf_Blight"
    assert _log_lines()[-1]["status"] == "ok"


def test_model_gets_the_uploaded_bytes_not_the_reencoded_copy(client, user, fake_model):
    img = jpeg_bytes(size=(300, 200))
    client.post("/api/camera/upload", files={"file": ("a.jpg", img, "image/jpeg")}, headers=user["headers"])
    assert fake_model == [len(img)]


# ---- Real model (slow) --------------------------------------
@pytest.mark.slow
def test_real_model_outputs_9_probabilities_summing_to_1():
    leafy = Image.new("RGB", (640, 480), (60, 140, 50))
    probs = inference.forward(inference.preprocess(png_bytes(leafy)))
    assert probs.shape == (9,) and probs.dtype == np.float32
    assert float(probs.min()) >= 0 and abs(float(probs.sum()) - 1.0) < 1e-3     # already softmaxed
    r = inference.predict(png_bytes(leafy), "Corn")
    assert r["status"] in ("ok", "unknown", "wrong_crop") and inference.is_loaded()
