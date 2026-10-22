# ============================================================
# GREEN App — Configuration
# Centralises all environment-dependent settings.
# Values are read from a .env file (or system environment).
# ============================================================

import os
from dotenv import load_dotenv

from db_url import normalize_database_url

# Load .env file from the project root (one level above /backend).
# Real environment variables win over .env (cPanel / tests must not be
# silently overridden by a developer's local file).
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), override=False)

# ---- App mode -----------------------------------------------
# Production by default: DEBUG must be enabled explicitly.
DEBUG: bool = os.getenv("DEBUG", "false").strip().lower() in ("1", "true", "yes")

# ---- Security -----------------------------------------------
# Mandatory in production. In DEBUG only, a fixed dev key is used so that
# tokens survive auto-reloads; it must never reach a deployed server.
_DEV_SECRET_KEY = "dev-only-insecure-secret-key"  # noqa: S105 (DEBUG only)
SECRET_KEY: str = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError(
            "SECRET_KEY is not set. Define it in the environment "
            "(e.g. python -c \"import secrets; print(secrets.token_urlsafe(48))\"), "
            "or set DEBUG=true for local development."
        )
    SECRET_KEY = _DEV_SECRET_KEY
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

# ---- Database -----------------------------------------------
# Production: Supabase PostgreSQL through the pooler (see .env.example).
# Fallback: SQLite for local development — file stored at project root
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(__file__), '..', 'green.db')
)
# postgres:// → postgresql://, sslmode=require added for PostgreSQL (db_url.py)
DATABASE_URL = normalize_database_url(DATABASE_URL)

# ---- Media (Green Data images) ------------------------------
# Analysed images are stored on the server disk, NOT in the database.
# The DB keeps only the path relative to MEDIA_DIR (e.g. "2026/10/<uuid>.jpg").
MEDIA_DIR: str = os.path.abspath(os.getenv(
    "MEDIA_DIR",
    os.path.join(os.path.dirname(__file__), '..', 'data', 'captures')
))
# URL prefix of the authenticated media endpoint (under /api so the
# Vercel rewrite proxies it too). On o2switch MEDIA_DIR must be outside
# public_html, e.g. /home/<account>/green_media.
MEDIA_URL_PREFIX: str = "/api/media"
# Maximum size of one uploaded image
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "8"))

# ---- Gemini AI (GreenBot chatbot + camera disease research) --
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
# Stable model listed on ai.google.dev/gemini-api/docs/models (checked 2026-10-22);
# Google recommends gemini-3.5-flash-lite for new projects: override here.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.1-flash-lite"

# ---- Weather API (OpenWeatherMap) --------------------------
WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "")
OPENWEATHER_BASE_URL: str = "https://api.openweathermap.org/data/2.5"

# ---- Drone / Camera (legacy) --------------------------------
DEFAULT_DRONE_IP: str = os.getenv("DEFAULT_DRONE_IP", os.getenv("DEFAULT_CAMERA_IP", "192.168.10.1"))
DEFAULT_DRONE_STREAM_PORT: int = int(os.getenv("DEFAULT_DRONE_STREAM_PORT", os.getenv("DEFAULT_CAMERA_PORT", "8080")))

DEFAULT_CAMERA_IP          = DEFAULT_DRONE_IP
DEFAULT_CAMERA_PORT        = DEFAULT_DRONE_STREAM_PORT

# ---- Models -------------------------------------------------
# Inference engine: "onnx" (production: onnxruntime, ~16 MB model, no
# PyTorch) or "torch" (development: needs torch + timm, see requirements.txt).
INFERENCE_BACKEND: str = os.getenv("INFERENCE_BACKEND", "onnx").strip().lower()
if INFERENCE_BACKEND not in ("onnx", "torch"):
    raise RuntimeError("INFERENCE_BACKEND must be 'onnx' or 'torch'.")
# Disease detection model (EfficientNet-B0 — cassava / maize / tomato)
_DEFAULT_MODEL = "best_efficientnet.onnx" if INFERENCE_BACKEND == "onnx" else "best_efficientnet.pth"
MODEL_PATH: str = os.getenv("MODEL_PATH", "").strip() or os.path.join(
    os.path.dirname(__file__), '..', 'Models', _DEFAULT_MODEL
)
# End-to-end tests only: deterministic fake predictions without loading the
# model. Honoured only when DEBUG is on, never in production.
E2E_FAKE_MODEL: bool = DEBUG and os.getenv("E2E_FAKE_MODEL", "") == "1"
# Stored with every analysis so the dataset knows which model predicted what
MODEL_VERSION: str = os.getenv("MODEL_VERSION", "efficientnet-v1")

# ---- RAG ----------------------------------------------------
RAG_CHUNKS_PATH: str = os.path.join(os.path.dirname(__file__), '..', 'rag', 'chunks.json')
RAG_EMBEDDINGS_PATH: str = os.path.join(os.path.dirname(__file__), '..', 'rag', 'embeddings_f32.bin')

# ---- Disease Database ---------------------------------------
DISEASES_DB_PATH: str = os.path.join(os.path.dirname(__file__), '..', 'diseases.json')

# ---- CORS ---------------------------------------------------
# Comma-separated list of allowed origins. Empty (default) = same-origin
# only: the frontend is served by FastAPI itself, so no CORS is needed.
# The API authenticates with a Bearer header, not cookies, so credentials
# are never allowed cross-origin; "*" is therefore safe but discouraged.
CORS_ORIGINS: list = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# ---- App ----------------------------------------------------
APP_NAME: str = "GREEN Agricultural Intelligence Platform"
APP_VERSION: str = "1.0.0"
