# ============================================================
# GREEN App — Plant disease classifier (TFLite, 9 classes)
#
#   Models/plant_classifier_float32.tflite   the model
#   Models/labels.txt                         class names, output order
#
# Preprocessing matches training exactly:
#   decode as RGB (alpha dropped) → resize to 224x224, bilinear with
#   antialiasing, stretched (no aspect ratio, no crop) → float32 pixels in
#   0–255, NOT normalized (the model normalizes internally) → [1, 224, 224, 3].
# Reference: tf.image.resize(image, (224, 224), method="bilinear", antialias=True).
# EXIF orientation is ignored on purpose: the model was trained with rotations.
#
# The output is already 9 probabilities summing to 1: no softmax here.
#
# Decision rule (one global threshold, never per class):
#   best = argmax over the 9 classes, confidence = its probability
#   crop of best ≠ chosen crop    → "wrong_crop"
#   confidence < threshold        → "unknown"
#   otherwise                     → "ok"
# Never renormalize over the chosen crop's 3 classes and never take the
# maximum over those 3 only: it inflates confidence on off-topic images
# (soil, hands, walls) and would hide the wrong_crop case.
# With no chosen crop, the crop check is skipped (analysis on all crops).
# ============================================================

import io
import json
import logging
import os
import threading
from datetime import UTC, datetime
from typing import Optional

import numpy as np
from PIL import Image

from config import CONFIDENCE_THRESHOLD, E2E_FAKE_MODEL, LABELS_PATH, MODEL_PATH, MODEL_VERSION, PREDICTION_LOG_PATH

logger = logging.getLogger(__name__)

INPUT_SIZE = 224
CROPS = ("Cassava", "Corn", "Tomato")

STATUS_OK = "ok"
STATUS_UNKNOWN = "unknown"
STATUS_WRONG_CROP = "wrong_crop"


# ============================================================
# LABELS  (index → class name; the crop is the first word)
# ============================================================
def _load_labels(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        labels = [line.strip() for line in f if line.strip()]
    for label in labels:
        if label.split()[0] not in CROPS:
            raise RuntimeError(f"{path}: the first word of '{label}' is not one of {CROPS}.")
    return labels


LABELS: list = _load_labels(LABELS_PATH)


def crop_of(label: str) -> str:
    return label.split()[0]


def is_healthy(label: str) -> bool:
    return label.split()[-1].lower() == "healthy"


def class_code(label: str) -> str:
    """Code used by the database and the knowledge base: "Corn leaf blight" → "Corn_Leaf_Blight"."""
    return "_".join(w.capitalize() for w in label.split())


CLASS_CODES: list = [class_code(label) for label in LABELS]
LABEL_BY_CODE: dict = dict(zip(CLASS_CODES, LABELS, strict=True))


def normalize_crop(value: Optional[str]) -> Optional[str]:
    """Crop sent with the request: Cassava, Corn or Tomato (any case). None if invalid."""
    v = (value or "").strip().capitalize()
    return v if v in CROPS else None


# ============================================================
# PREPROCESSING
# ============================================================
def preprocess(image_bytes: bytes) -> np.ndarray:
    """Raw image bytes → float32 array [1, 224, 224, 3], RGB, values 0–255."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            rgb = img.convert("RGB")             # 3 channels, alpha dropped
    except Exception as exc:
        raise ValueError(f"Cannot decode image: {exc}") from exc
    # Each channel is resized in 32-bit float ("F" mode) so the result is not
    # rounded to integers, as with tf.image.resize. Pillow's BILINEAR resize
    # widens the kernel when downscaling: that is the antialiasing.
    planes = [
        np.asarray(band.convert("F").resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR), dtype=np.float32)
        for band in rgb.split()
    ]
    return np.stack(planes, axis=-1)[None]


# ============================================================
# INTERPRETER  (one per process, created once, guarded by a lock)
# The TFLite interpreter is not thread-safe: loading and every
# set_tensor / invoke / get_tensor sequence run under _lock.
# Under Passenger each worker process has its own interpreter.
# ============================================================
_interpreter = None
_lock = threading.Lock()


def _interpreter_class():
    try:
        from ai_edge_litert.interpreter import Interpreter   # LiteRT (light)
        return Interpreter
    except ImportError:
        pass
    try:
        from tflite_runtime.interpreter import Interpreter    # former name of LiteRT
        return Interpreter
    except ImportError:
        pass
    try:
        import tensorflow as tf
        return tf.lite.Interpreter
    except ImportError:
        raise RuntimeError("No TFLite runtime: install ai-edge-litert (or tensorflow).") from None


def _load_locked():
    global _interpreter
    if _interpreter is None:
        logger.info("Loading TFLite model from %s", MODEL_PATH)
        interp = _interpreter_class()(model_path=MODEL_PATH, num_threads=2)  # shared hosting CPU quota
        interp.allocate_tensors()
        inp = interp.get_input_details()[0]
        out = interp.get_output_details()[0]
        if list(inp["shape"]) != [1, INPUT_SIZE, INPUT_SIZE, 3] or inp["dtype"] != np.float32:
            raise RuntimeError(f"Unexpected model input {list(inp['shape'])} {inp['dtype']}.")
        if int(np.prod(out["shape"])) != len(LABELS):
            raise RuntimeError(f"Model has {int(np.prod(out['shape']))} outputs, labels.txt has {len(LABELS)}.")
        _interpreter = interp
        logger.info("Model %s loaded: %d classes, threshold %.2f.", MODEL_VERSION, len(LABELS), CONFIDENCE_THRESHOLD)
    return _interpreter


def is_loaded() -> bool:
    return _interpreter is not None


def load() -> None:
    """Create the interpreter now (warm-up)."""
    with _lock:
        _load_locked()


def forward(x: np.ndarray) -> np.ndarray:
    """Preprocessed input → the 9 probabilities, as returned by the model."""
    with _lock:
        interp = _load_locked()
        interp.set_tensor(interp.get_input_details()[0]["index"], x)
        interp.invoke()
        probs = interp.get_tensor(interp.get_output_details()[0]["index"])
    return np.asarray(probs, dtype=np.float32).reshape(-1).copy()


# ============================================================
# DECISION RULE
# ============================================================
SEVERITY_THRESHOLDS = {"high": 0.80, "medium": 0.55}   # UI alert level of a disease, not damage


def _severity(confidence: float, healthy: bool) -> str:
    if healthy:
        return "none"
    if confidence >= SEVERITY_THRESHOLDS["high"]:
        return "high"
    return "medium" if confidence >= SEVERITY_THRESHOLDS["medium"] else "low"


def decide(probs: np.ndarray, chosen_crop: Optional[str], threshold: float = CONFIDENCE_THRESHOLD) -> tuple:
    """(status, best index, confidence) from the 9 probabilities, unchanged."""
    best = int(np.argmax(probs))
    confidence = float(probs[best])
    if chosen_crop is not None and crop_of(LABELS[best]) != chosen_crop:
        return STATUS_WRONG_CROP, best, confidence
    if confidence < threshold:
        return STATUS_UNKNOWN, best, confidence
    return STATUS_OK, best, confidence


def build_result(probs: np.ndarray, chosen_crop: Optional[str]) -> dict:
    from knowledge import class_name   # display names (FR/EN) live in the knowledge base

    status, best, confidence = decide(probs, chosen_crop)
    label = LABELS[best]
    code = CLASS_CODES[best]
    healthy = is_healthy(label)
    top3 = [
        {"code": CLASS_CODES[i], "class": LABELS[i], "confidence": round(float(probs[i]) * 100, 1)}
        for i in np.argsort(-probs)[:3].tolist()
    ]
    return {
        # Traceable result (API contract)
        "status":           status,
        "disease":          label if status == STATUS_OK else None,
        "confidence":       round(confidence, 4),
        "chosen_crop":      chosen_crop,
        "model_version":    MODEL_VERSION,
        "threshold":        CONFIDENCE_THRESHOLD,
        # Details: best class among the 9 whatever the status, all probabilities
        "best":             label,
        "probabilities":    {LABELS[i]: round(float(p), 6) for i, p in enumerate(probs)},
        # Fields stored with an "ok" analysis
        "class_raw":        code,
        "detected_disease": "healthy" if healthy else code,
        "disease_name":     class_name(code, "en"),
        "plant_type":       crop_of(label),
        "severity":         _severity(confidence, healthy),
        "top3":             top3,
    }


def predict(image_bytes: bytes, chosen_crop: Optional[str] = None) -> dict:
    """Run the classifier on raw image bytes and apply the decision rule."""
    if E2E_FAKE_MODEL:
        return build_result(_fake_probs(image_bytes), chosen_crop)
    return build_result(forward(preprocess(image_bytes)), chosen_crop)


def _fake_probs(image_bytes: bytes) -> np.ndarray:
    """E2E tests (DEBUG + E2E_FAKE_MODEL=1): probabilities chosen from the image colour."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((8, 8))
    r, g, b = (float(np.mean(c)) for c in np.asarray(image, dtype=np.float32).reshape(-1, 3).T)
    probs = np.full(len(LABELS), 0.0, dtype=np.float32)
    top = int(r + 2 * g + 3 * b) % len(LABELS)
    probs[top] = 0.71 + (int(r) % 29) / 100       # always above the 0.70 default: E2E flows get an answer
    probs[(top + 1) % len(LABELS)] = 1.0 - probs[top]
    return probs


# ============================================================
# PREDICTION LOG  (JSON lines, used to retune the threshold)
# Never contains the image.
# ============================================================
_log_lock = threading.Lock()


def log_prediction(result: dict, *, source: Optional[str] = None, crop_source: Optional[str] = None) -> None:
    entry = {
        "timestamp":     datetime.now(UTC).isoformat(timespec="milliseconds"),
        "chosen_crop":   result["chosen_crop"],
        "crop_source":   crop_source,          # "request" | "parcel" | None (all crops)
        "source":        source,               # camera | rover | upload
        "probabilities": result["probabilities"],
        "best":          result["best"],
        "confidence":    result["confidence"],
        "status":        result["status"],
        "model_version": result["model_version"],
        "threshold":     result["threshold"],
    }
    logger.info("prediction status=%s best=%s conf=%.4f crop=%s", entry["status"], entry["best"],
                entry["confidence"], entry["chosen_crop"])
    try:
        line = json.dumps(entry, ensure_ascii=False)
        with _log_lock:
            os.makedirs(os.path.dirname(PREDICTION_LOG_PATH), exist_ok=True)
            with open(PREDICTION_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError as exc:   # the log must never break an analysis
        logger.error("Cannot write the prediction log %s: %s", PREDICTION_LOG_PATH, exc)
