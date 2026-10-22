# ============================================================
# GREEN App — Rover / Drone shared logic
# MJPEG stream check, frame grab, disease inference, fiche build.
# ============================================================

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple

import httpx
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from config import DEFAULT_DRONE_IP, DEFAULT_DRONE_STREAM_PORT, MODEL_VERSION
from inference import predict
from knowledge import build_fiche, class_code, fiche_for_analysis
from media import ProcessedImage, media_url, process_image, save_image
from models import DiseaseAnalysis, Parcel, User

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rover_inf")

def parse_ip_port(payload: dict) -> Tuple[str, int]:
    ip = (payload.get("ip") or DEFAULT_DRONE_IP).strip()
    try:
        port = int(payload.get("port") or DEFAULT_DRONE_STREAM_PORT)
    except (TypeError, ValueError):
        port = DEFAULT_DRONE_STREAM_PORT
    return ip, port


def stream_url(ip: str, port: int = None) -> str:
    port = port or DEFAULT_DRONE_STREAM_PORT
    return f"http://{ip}:{port}/"


async def check_stream(ip: str, port: int = None) -> bool:
    """Verify MJPEG endpoint responds (GET with partial read; HEAD is unreliable)."""
    url = stream_url(ip, port)
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            async with client.stream("GET", url) as response:
                if response.status_code >= 500:
                    return False
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        return True
                return response.status_code < 400
    except Exception:
        return False


async def grab_frame(ip: str, port: int = None) -> bytes:
    """Download the first complete JPEG from an MJPEG stream."""
    url = stream_url(ip, port)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream("GET", url) as response:
                buffer = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=16384):
                    buffer.extend(chunk)
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9", start + 2) if start != -1 else -1
                    if start != -1 and end != -1:
                        return bytes(buffer[start : end + 2])
                    if len(buffer) > 2 * 1024 * 1024:
                        break
    except Exception as exc:
        logger.error(f"Frame grab error from {url}: {exc}")
        raise HTTPException(
            status_code=502,
            detail=(
                f"Could not grab a frame from the stream at {url}. "
                "Check the rover Wi-Fi and the IP/port."
            ),
        )
    raise HTTPException(status_code=502, detail="No JPEG frame found in stream.")


async def run_disease_model(image_bytes: bytes) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, predict, image_bytes)


def save_analysis(
    db: Session,
    current_user: User,
    disease: dict,
    image: Optional[ProcessedImage],
    image_path: Optional[str],
    source: str,
    parcel_id: Optional[int],
    latitude: Optional[float],
    longitude: Optional[float],
    lang: str = "en",
) -> DiseaseAnalysis:
    # Snapshot of the sheet at analysis time; responses rebuild it in the reader's language
    fiche = build_fiche(
        detected_disease=disease["detected_disease"], plant_type=disease["plant_type"],
        confidence=disease["confidence"], severity=disease["severity"], top3=disease.get("top3"),
        source=source, parcel_id=parcel_id, latitude=latitude, longitude=longitude, lang=lang,
    )

    analysis = DiseaseAnalysis(
        user_id          = current_user.id,
        parcel_id        = parcel_id,
        source           = source,
        image_path       = image_path,
        image_sha256     = image.sha256 if image else None,
        image_bytes      = len(image.jpeg) if image and image_path else None,
        image_width      = image.width if image else None,
        image_height     = image.height if image else None,
        detected_disease = disease["detected_disease"],
        disease_name     = disease["disease_name"],
        confidence       = disease["confidence"],
        severity         = disease["severity"],
        plant_type       = disease["plant_type"],
        predictions      = disease.get("top3"),
        model_version    = MODEL_VERSION,
        consent_dataset  = bool(current_user.dataset_consent),
        latitude         = latitude,
        longitude        = longitude,
        fiche_terrain    = fiche,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def analysis_response(analysis: DiseaseAnalysis, disease: dict, lang: str, duplicate: bool = False) -> dict:
    return {
        "success":       True,
        "analysis_id":   analysis.id,
        "duplicate":     duplicate,
        "image_path":    media_url(analysis.image_path, analysis.user_id),
        "thumb_path":    media_url(analysis.image_path, analysis.user_id, thumb=True),
        "disease":       disease,
        "fiche_terrain": fiche_for_analysis(analysis, lang),
    }


def _stored_disease(a: DiseaseAnalysis) -> dict:
    """The `disease` block of a previous analysis (duplicate upload)."""
    return {
        "class_raw":        class_code(a.detected_disease, a.plant_type),
        "detected_disease": a.detected_disease,
        "disease_name":     a.disease_name,
        "plant_type":       a.plant_type,
        "confidence":       a.confidence,
        "severity":         a.severity,
        "top3":             a.predictions or [],
    }


async def analyze_image_bytes(
    image_bytes: bytes,
    db: Session,
    current_user: User,
    source: str,
    parcel_id: Optional[int] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    save_image_file: bool = True,
    lang: str = "en",
) -> dict:
    if parcel_id is not None:
        owned = db.query(Parcel.id).filter(Parcel.id == parcel_id, Parcel.user_id == current_user.id).first()
        if not owned:
            raise HTTPException(status_code=404, detail="Parcel not found.")

    image = await run_in_threadpool(process_image, image_bytes)

    # The same photo sent twice by the same user is not analysed again.
    previous = (
        db.query(DiseaseAnalysis)
          .filter(DiseaseAnalysis.user_id == current_user.id,
                  DiseaseAnalysis.image_sha256 == image.sha256)
          .order_by(DiseaseAnalysis.id)
          .first()
    )
    if previous is not None:
        return analysis_response(previous, _stored_disease(previous), lang, duplicate=True)

    # Position typed or sent by the browser wins; otherwise the photo's own
    # EXIF GPS, kept only if the user agreed to it.
    if latitude is None and longitude is None and image.gps and current_user.location_consent:
        latitude, longitude = image.gps

    # Inference first: the image is only kept if the analysis succeeded
    disease = await run_disease_model(image.jpeg)
    image_path = save_image(image) if save_image_file else None
    analysis = save_analysis(
        db, current_user, disease, image, image_path, source,
        parcel_id, latitude, longitude, lang,
    )
    return analysis_response(analysis, disease, lang)
