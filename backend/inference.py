# ============================================================
# GREEN App — EfficientNet Disease Inference Engine
#
# Loads the best_efficientnet.pth model once at startup and
# exposes a single `predict(image_bytes)` function used by
# the drone router and upload endpoint.
#
# Architecture: timm EfficientNet-B0 (1280-d features → 11 classes)
#
# ⚠️  CLASS ORDER — MUST MATCH TRAINING
# The list below maps output index → class label.
# If predictions look wrong, reorder this list to match the
# alphabetical order of your training dataset folders.
# ============================================================

import io
import logging
import threading

import numpy as np
from PIL import Image

from config import E2E_FAKE_MODEL, INFERENCE_BACKEND, MODEL_PATH

logger = logging.getLogger(__name__)

# torch and torchvision are imported lazily inside functions so that
# importing this module does not block the server startup.


# ============================================================
# CLASS NAMES  (index → label)
# 11 classes — must match the EXACT training folder order.
#
# ⚠️  ORDER WARNING
# PyTorch ImageFolder sorts folder names with Python's built-in
# sort(), which is case-sensitive (uppercase A–Z before lowercase).
# The order below assumes Linux case-sensitive alphabetical sort
# of the original training folder names:
#   "Cassava mosaic", "Corn brown spots", "Corn healthy",
#   "Corn leaf blight", "Corn mildew", "Corn streak",
#   "Corn stripe", "Corn yellowing", "Tomato Brown Spots",
#   "Tomato blight leaf", "Tomato healthy"
# If predictions look wrong, reorder this list to match your
# training folder alphabetical order exactly.
# ============================================================
CLASS_NAMES = [
    "Cassava_Mosaic",       # 0  ← "Cassava mosaic"
    "Corn_Brown_Spots",     # 1  ← "Corn brown spots"
    "Corn_Healthy",         # 2  ← "Corn healthy"
    "Corn_Leaf_Blight",     # 3  ← "Corn leaf blight"
    "Corn_Mildew",          # 4  ← "Corn mildew"
    "Corn_Streak",          # 5  ← "Corn streak"
    "Corn_Stripe",          # 6  ← "Corn stripe"
    "Corn_Yellowing",       # 7  ← "Corn yellowing"
    "Tomato_Brown_Spots",   # 8  ← "Tomato Brown Spots"
    "Tomato_Blight_Leaf",   # 9  ← "Tomato blight leaf"
    "Tomato_Healthy",       # 10 ← "Tomato healthy"
]

# "Healthy" class names — used to set detected_disease = "healthy" in the DB
HEALTHY_CLASSES = {"Corn_Healthy", "Tomato_Healthy"}

# Maps class name prefix → plant type stored in DB (English)
PLANT_TYPE_MAP = {
    "Cassava": "Cassava",
    "Corn":    "Corn",
    "Tomato":  "Tomato",
}

# Human-readable English display names for each class (API response)
CLASS_EN_NAMES: dict[str, str] = {
    "Cassava_Mosaic":     "Cassava Mosaic",
    "Corn_Brown_Spots":   "Corn Brown Spots",
    "Corn_Healthy":       "Healthy Corn",
    "Corn_Leaf_Blight":   "Corn Leaf Blight",
    "Corn_Mildew":        "Corn Mildew",
    "Corn_Streak":        "Corn Streak",
    "Corn_Stripe":        "Corn Stripe",
    "Corn_Yellowing":     "Corn Yellowing",
    "Tomato_Brown_Spots": "Tomato Brown Spots",
    "Tomato_Blight_Leaf": "Tomato Blight Leaf",
    "Tomato_Healthy":     "Healthy Tomato",
}

# Human-readable French display names for each class (for reference/translation)
CLASS_FR_NAMES: dict[str, str] = {
    "Cassava_Mosaic":     "Mosaïque du manioc",
    "Corn_Brown_Spots":   "Taches brunes du maïs",
    "Corn_Healthy":       "Maïs sain",
    "Corn_Leaf_Blight":   "Brûlure foliaire du maïs",
    "Corn_Mildew":        "Mildiou du maïs",
    "Corn_Streak":        "Stries du maïs",
    "Corn_Stripe":        "Rayures du maïs",
    "Corn_Yellowing":     "Jaunissement du maïs",
    "Tomato_Brown_Spots": "Taches brunes de la tomate",
    "Tomato_Blight_Leaf": "Brûlure foliaire de la tomate",
    "Tomato_Healthy":     "Tomate saine",
}

# Alert level of a DISEASE prediction, derived from the model confidence.
# It is not a measure of damage: the classifier cannot estimate that.
# Healthy predictions always get "none". The UI labels it accordingly.
SEVERITY_THRESHOLDS = {
    "high":   0.80,   # ≥ 80 %
    "medium": 0.55,   # 55–79 %
    "low":    0.0,    # < 55 %
}


# ============================================================
# IMAGE PRE-PROCESSING
# The ONNX path reproduces torchvision's PIL pipeline with PIL + numpy:
# Resize(256) (shorter side, bilinear) → CenterCrop(224) → ToTensor →
# Normalize(ImageNet). Parity is checked by scripts/onnx_parity.py.
# ============================================================
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


def preprocess_np(image: Image.Image) -> np.ndarray:
    """(1, 3, 224, 224) float32, identical to the torchvision transform below."""
    w, h = image.size
    short, long_ = (w, h) if w <= h else (h, w)
    new_short, new_long = 256, int(256 * long_ / short)
    size = (new_short, new_long) if w <= h else (new_long, new_short)
    img = image.resize(size, Image.BILINEAR)
    w, h = img.size
    top, left = int(round((h - 224) / 2.0)), int(round((w - 224) / 2.0))
    img = img.crop((left, top, left + 224, top + 224))
    x = np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0
    return ((x - IMAGENET_MEAN) / IMAGENET_STD)[None].astype(np.float32)


_transform = None

def _get_transform():
    """Return the torchvision transform pipeline, building it on first call."""
    global _transform
    if _transform is None:
        from torchvision import transforms  # lazy import
        _transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std =[0.229, 0.224, 0.225],
            ),
        ])
    return _transform


# ============================================================
# MODEL LOADER  (singleton — loaded once at first call)
# Under Passenger (a2wsgi) the ASGI lifespan does not run, so the warm-up
# thread may not exist: loading is lazy and guarded by a lock so that two
# first requests never load the model twice.
# ============================================================
_model = None   # type: ignore[assignment]
_session = None
_load_lock = threading.Lock()


def _onnx_session():
    global _session
    if _session is None:
        with _load_lock:
            if _session is None:
                import onnxruntime as ort  # lazy import

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2   # shared hosting: stay within the CPU quota
                opts.inter_op_num_threads = 1
                logger.info(f"Loading ONNX model from {MODEL_PATH}")
                _session = ort.InferenceSession(MODEL_PATH, sess_options=opts, providers=["CPUExecutionProvider"])
    return _session


def is_loaded() -> bool:
    return (_session if INFERENCE_BACKEND == "onnx" else _model) is not None


def load() -> None:
    """Load the configured engine now (warm-up)."""
    if INFERENCE_BACKEND == "onnx":
        _onnx_session()
    else:
        get_model()


def _build_efficientnet(num_classes: int, state_dict_keys: list):
    """
    Reconstruct the exact EfficientNet-B0 architecture used during training
    by inspecting the saved state-dict keys.

    Three possible formats:
    ┌──────────────────────────────────────────────────────────────┐
    │ Format A — timm backbone + Sequential head (custom training) │
    │   Keys: conv_stem.*, blocks.*, classifier.1.*               │
    │   Build: timm backbone, replace classifier with             │
    │           nn.Sequential(Dropout, Linear)                    │
    ├──────────────────────────────────────────────────────────────┤
    │ Format B — standard timm (direct Linear head)               │
    │   Keys: conv_stem.*, classifier.weight                      │
    │   Build: timm.create_model(num_classes=N)                   │
    ├──────────────────────────────────────────────────────────────┤
    │ Format C — torchvision                                       │
    │   Keys: features.*, classifier.1.*                          │
    │   Build: torchvision efficientnet_b0, replace head          │
    └──────────────────────────────────────────────────────────────┘
    """
    has_conv_stem  = any("conv_stem" in k for k in state_dict_keys)
    has_cls1       = any("classifier.1" in k for k in state_dict_keys)

    import torch  # lazy import

    # ── Format A: timm backbone + manual Sequential head ──────
    if has_conv_stem and has_cls1:
        try:
            import timm  # type: ignore
            model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=num_classes)
            in_features = model.classifier.in_features
            model.classifier = torch.nn.Sequential(
                torch.nn.Dropout(p=0.2, inplace=True),
                torch.nn.Linear(in_features, num_classes),
            )
            logger.info("Model built: timm backbone + Sequential head (Format A).")
            return model
        except ImportError:
            pass

    # ── Format B: standard timm ───────────────────────────────
    if has_conv_stem and not has_cls1:
        try:
            import timm  # type: ignore
            model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=num_classes)
            logger.info("Model built: standard timm efficientnet_b0 (Format B).")
            return model
        except ImportError:
            pass

    # ── Format C: torchvision (fallback) ──────────────────────
    from torchvision.models import efficientnet_b0
    model = efficientnet_b0(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = torch.nn.Linear(in_features, num_classes)
    logger.info("Model built: torchvision efficientnet_b0 (Format C).")
    return model


def get_model():
    """Return the loaded PyTorch model (lazy singleton — imports torch on first call)."""
    global _model
    if _model is not None:
        return _model
    with _load_lock:
        return _load_torch()


def _load_torch():
    global _model
    if _model is None:
        import torch  # lazy import
        # Limit CPU threads to prevent CPU context-switch thrashing
        if getattr(torch, "set_num_threads", None):
            torch.set_num_threads(2)
            
        logger.info(f"Loading EfficientNet model from {MODEL_PATH}")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        state_dict = torch.load(MODEL_PATH, map_location=device)

        # Unwrap checkpoint wrappers
        if isinstance(state_dict, dict) and "state_dict" in state_dict:
            state_dict = state_dict["state_dict"]
        elif isinstance(state_dict, dict) and "model_state_dict" in state_dict:
            state_dict = state_dict["model_state_dict"]

        model = _build_efficientnet(
            num_classes=len(CLASS_NAMES),
            state_dict_keys=list(state_dict.keys()),
        )
        model.load_state_dict(state_dict, strict=True)
        model.to(device)
        model.eval()
        _model = model
        logger.info(f"Model loaded on {device} — {len(CLASS_NAMES)} classes.")

    return _model


# ============================================================
# INFERENCE FUNCTION
# ============================================================
def _get_severity(confidence: float, is_healthy: bool = False) -> str:
    if is_healthy:
        return "none"
    if confidence >= SEVERITY_THRESHOLDS["high"]:
        return "high"
    if confidence >= SEVERITY_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def _softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max()
    e = np.exp(z)
    return e / e.sum()


def forward_probs(image: Image.Image, backend: str = None) -> np.ndarray:
    """Class probabilities (11,) for a PIL RGB image with the given engine."""
    backend = backend or INFERENCE_BACKEND
    if backend == "onnx":
        session = _onnx_session()
        logits = session.run(None, {session.get_inputs()[0].name: preprocess_np(image)})[0][0]
        return _softmax(logits.astype(np.float64)).astype(np.float32)

    import torch                    # lazy — already cached by Python after first import
    import torch.nn.functional as F

    model = get_model()
    device = next(model.parameters()).device
    tensor = _get_transform()(image).unsqueeze(0).to(device)
    with torch.inference_mode():   # fully disables autograd (faster than no_grad)
        return F.softmax(model(tensor), dim=1)[0].cpu().numpy()


def predict(image_bytes: bytes) -> dict:
    """
    Run EfficientNet inference on raw image bytes.

    Returns:
        {
            "class_raw":       str,    # e.g. "Corn_Leaf_Blight"
            "detected_disease": str,   # disease ID for the DB ("healthy" if healthy)
            "disease_name":    str,    # human-readable label
            "plant_type":      str,    # "tomate" | "maïs" | "manioc"
            "confidence":      float,  # 0.0 – 1.0
            "severity":        str,    # "none" (healthy) | "low" | "medium" | "high" (alert level)
            "top3":            list,   # [{class, confidence}, ...] for display
        }
    """
    if E2E_FAKE_MODEL:
        return _fake_predict(image_bytes)

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"Cannot decode image: {exc}") from exc

    probs = forward_probs(image)
    # Top-1 prediction
    class_idx = int(np.argmax(probs))
    confidence = float(probs[class_idx])
    class_raw  = CLASS_NAMES[class_idx]

    # Derive plant type and disease ID
    prefix     = class_raw.split("_")[0]            # "Cassava" | "Corn" | "Tomato"
    plant_type = PLANT_TYPE_MAP.get(prefix, prefix.lower())
    is_healthy = class_raw in HEALTHY_CLASSES

    # Build a human-readable disease name
    if is_healthy:
        disease_name     = CLASS_EN_NAMES.get(class_raw, "Healthy")
        detected_disease = "healthy"
    else:
        disease_name     = CLASS_EN_NAMES.get(class_raw, class_raw.replace("_", " "))
        detected_disease = class_raw  # used as disease ID in the DB

    # Top-3 for the fiche terrain display
    top3_indices = np.argsort(-probs)[:3].tolist()
    top3 = [
        {
            "code":       CLASS_NAMES[i],
            "class":      CLASS_NAMES[i].replace("_", " "),
            "confidence": round(float(probs[i]) * 100, 1),
        }
        for i in top3_indices
    ]

    return {
        "class_raw":        class_raw,
        "detected_disease": detected_disease,
        "disease_name":     disease_name,
        "plant_type":       plant_type,
        "confidence":       round(confidence, 4),
        "severity":         _get_severity(confidence, is_healthy),
        "top3":             top3,
    }


def _fake_predict(image_bytes: bytes) -> dict:
    """E2E tests (DEBUG + E2E_FAKE_MODEL=1): class chosen from the image colour."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((8, 8))
    r, g, b = (sum(c) / len(c) for c in zip(*image.getdata(), strict=True))
    class_raw = CLASS_NAMES[int(r + 2 * g + 3 * b) % len(CLASS_NAMES)]
    is_healthy = class_raw in HEALTHY_CLASSES
    confidence = 0.6 + (int(r) % 40) / 100
    return {
        "class_raw":        class_raw,
        "detected_disease": "healthy" if is_healthy else class_raw,
        "disease_name":     CLASS_EN_NAMES[class_raw],
        "plant_type":       PLANT_TYPE_MAP[class_raw.split("_")[0]],
        "confidence":       round(confidence, 4),
        "severity":         _get_severity(confidence, is_healthy),
        "top3": [
            {"code": class_raw, "class": class_raw.replace("_", " "), "confidence": round(confidence * 100, 1)},
        ],
    }
