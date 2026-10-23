# ============================================================
# GREEN App — FastAPI Application Entry Point
#
# Run the server:
#   cd backend
#   uvicorn main:app --reload --port 8000
#
# API docs available at: http://localhost:8000/docs
# ============================================================

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import APP_NAME, APP_VERSION, CORS_ORIGINS, DEBUG
from database import engine, IS_SQLITE

# ---- Import routers -----------------------------------------
from routers import auth_router
from routers import dashboard_router   # Phase 3 — KPIs + trends
from routers import analysis_router    # Phase 3 — Analysis history + fiche terrain
from routers import camera_router      # Phase MVP — Rover camera + dual inference
from routers import parcel_router      # Phase 5 — Parcel CRUD
from routers import chatbot_router     # Phase 6 — GreenBot RAG + Gemini API
from routers import weather_router     # Phase 6 — OpenWeatherMap proxy
from routers import diseases_router    # Disease reference database
from routers import media_router       # Authenticated access to analysed images
from routers import mission_router     # GREEN Map missions (grid, path, heatmap)
from routers import green_data_router  # GREEN Data aggregates (partner / admin)

logger = logging.getLogger(__name__)

# ---- Database schema ----------------------------------------
# SQLite (local development): migrated to the latest revision at startup.
# PostgreSQL: `alembic upgrade head` is a deployment step; the app only
# warns when the schema is behind.
if IS_SQLITE:
    from schema_check import migrate_sqlite
    migrate_sqlite(engine)
else:
    from schema_check import warn_if_schema_outdated
    warn_if_schema_outdated(engine)


def _warmup_models():
    """Load EfficientNet in a background thread."""
    import time
    import threading

    def load_efficientnet():
        try:
            from inference import load
            load()
            logger.info("[Warmup] EfficientNet ready.")
        except Exception as e:
            logger.error(f"[Warmup] EfficientNet FAILED to load: {e}")

    def load_rag():
        try:
            from routers.chatbot_router import _load_rag
            _load_rag()
            logger.info("[Warmup] RAG index ready.")
        except Exception as e:
            logger.error(f"[Warmup] RAG index FAILED to load: {e}")

    # Brief pause so the ASGI loop finishes binding before we hit the CPU hard
    time.sleep(1)
    logger.info("[Warmup] Loading EfficientNet in background...")

    t1 = threading.Thread(target=load_efficientnet, daemon=True)
    t1.start()
    t1.join()

    # RAG is lighter — load it after the heavy models
    load_rag()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan: runs startup logic then yields control to the server.
    Models are loaded lazily on their first request so the server
    starts accepting requests immediately without hanging the ASGI event loop.
    """
    import threading
    logger.info("[Startup] GREEN server ready — scheduling parallel AI warmup.")
    threading.Thread(target=_warmup_models, daemon=True).start()

    yield

    logger.info("[Shutdown] GREEN server stopped.")


# ---- FastAPI App Instance -----------------------------------
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Agricultural AI platform for Cameroonian agribusiness enterprises.",
    debug=DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
)

# ---- Security headers (any host: Passenger, uvicorn) ----------
# HSTS is set by the web server for HTTPS only (deploy/o2switch/htaccess-snippet.conf).
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(self), geolocation=(self), microphone=()",
}


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


# ---- Translated error messages (Accept-Language / ?lang=) ---
import i18n  # noqa: E402
i18n.install(app)

# ---- CORS Middleware ----------------------------------------
# Only needed when the frontend is hosted on another origin (e.g. Vercel).
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept-Language"],
    )

# ---- Register API Routers -----------------------------------
app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(analysis_router.router)
app.include_router(media_router.router)
app.include_router(mission_router.router)
app.include_router(green_data_router.router)
app.include_router(camera_router.router)
app.include_router(parcel_router.router)
app.include_router(chatbot_router.router)
app.include_router(weather_router.router)
app.include_router(diseases_router.router)

# ---- Serve Frontend Static Files ----------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

# ---- HTML Page Routes ---------------------------------------
# Defined BEFORE the StaticFiles mount so FastAPI routes take priority.

@app.get("/", include_in_schema=False)
async def login_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/register", include_in_schema=False)
async def register_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "register.html"))


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))


# Legacy drone page: the rover camera page replaced it.
@app.get("/drone", include_in_schema=False)
@app.get("/drone.html", include_in_schema=False)
async def drone_page():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/camera")


@app.get("/camera", include_in_schema=False)
async def camera_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "camera.html"))


@app.get("/history", include_in_schema=False)
async def history_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "history.html"))


@app.get("/profile", include_in_schema=False)
async def profile_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "profile.html"))


@app.get("/settings", include_in_schema=False)
async def settings_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "settings.html"))


@app.get("/marketplace", include_in_schema=False)
async def marketplace_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "marketplace.html"))


@app.get("/chatbot", include_in_schema=False)
async def chatbot_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "chatbot.html"))


@app.get("/map", include_in_schema=False)
async def map_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "map.html"))


@app.get("/calendar", include_in_schema=False)
async def calendar_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "calendar.html"))


@app.get("/diseases", include_in_schema=False)
async def diseases_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "diseases.html"))


@app.get("/economics", include_in_schema=False)
async def economics_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "economics.html"))


@app.get("/green-data", include_in_schema=False)
async def green_data_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "green-data.html"))


@app.get("/benchmark", include_in_schema=False)
async def benchmark_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "benchmark.html"))


# ---- Health Check + Warmup status --------------------------
@app.get("/api/health", tags=["Health"])
async def health_check():
    """Returns server status and which models are already loaded."""
    from config import GEMINI_API_KEY, INFERENCE_BACKEND, MODEL_VERSION, WEATHER_API_KEY
    from inference import is_loaded
    from routers.chatbot_router import _chunks
    return {
        "status":            "ok",
        "app":               APP_NAME,
        "version":           APP_VERSION,
        "model_version":     MODEL_VERSION,
        "models": {
            "efficientnet":  "ready" if is_loaded() else "lazy",
            "inference_backend": INFERENCE_BACKEND,
            "rag_index":     "ready" if len(_chunks) > 0             else "lazy",
        },
        # Optional services: false = feature disabled with a clear message in the UI
        "services": {
            "greenbot": bool(GEMINI_API_KEY),
            "weather":  bool(WEATHER_API_KEY),
        },
    }


# Analysed images are NOT mounted publicly: see routers/media_router.py.
# Captures saved there by older versions must not be served either.
@app.get("/assets/captures/{path:path}", include_in_schema=False)
async def legacy_captures(path: str):
    raise HTTPException(status_code=404, detail="Not Found")

# ---- Mount static assets ------------------------------------
app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend"
)
