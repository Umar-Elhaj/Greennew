# ============================================================
# GREEN App — Configuration
# Centralises all environment-dependent settings.
# Values are read from a .env file (or system environment).
# ============================================================

import os
from dotenv import load_dotenv

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
# Production: Supabase PostgreSQL (session pooler URI, see .env).
# Fallback: SQLite for local development — file stored at project root
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(__file__), '..', 'green.db')
)
# SQLAlchemy needs the "postgresql://" scheme (Supabase sometimes shows "postgres://")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ---- Media (Green Data images) ------------------------------
# Analysed images are stored on the server disk, NOT in the database.
# The DB keeps only the path relative to MEDIA_DIR (e.g. "2026/10/<uuid>.jpg").
MEDIA_DIR: str = os.path.abspath(os.getenv(
    "MEDIA_DIR",
    os.path.join(os.path.dirname(__file__), '..', 'data', 'captures')
))
# Public URL prefix — under /api so the Vercel rewrite proxies it too
MEDIA_URL_PREFIX: str = "/api/media"

# ---- Gemini AI (GreenBot chatbot + camera disease research) --
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-3.1-flash-lite"   # Stable, budget-friendly; 2.5-flash-lite is restricted for new API keys

# ---- Weather API (OpenWeatherMap) --------------------------
WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "")
OPENWEATHER_BASE_URL: str = "https://api.openweathermap.org/data/2.5"

# ---- Drone / Camera (legacy) --------------------------------
DEFAULT_DRONE_IP: str = os.getenv("DEFAULT_DRONE_IP", os.getenv("DEFAULT_CAMERA_IP", "192.168.10.1"))
DEFAULT_DRONE_STREAM_PORT: int = int(os.getenv("DEFAULT_DRONE_STREAM_PORT", os.getenv("DEFAULT_CAMERA_PORT", "8080")))

DEFAULT_CAMERA_IP          = DEFAULT_DRONE_IP
DEFAULT_CAMERA_PORT        = DEFAULT_DRONE_STREAM_PORT

# ---- Models -------------------------------------------------
# Disease detection model (EfficientNet — cassava / maize / tomato)
MODEL_PATH: str = os.getenv(
    "MODEL_PATH",
    os.path.join(os.path.dirname(__file__), '..', 'Models', 'best_efficientnet.pth')
)
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
