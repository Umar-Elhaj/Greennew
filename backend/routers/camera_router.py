# ============================================================
# GREEN App — Camera / Rover Router (MVP)
#
#   POST /api/camera/connect        → verify MJPEG stream reachable
#   POST /api/camera/capture        → grab frame + disease inference
#   POST /api/camera/analyze-frame  → analyse browser-captured frame
#   POST /api/camera/upload         → analyse uploaded image file
# ============================================================

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User
from i18n import request_lang
from media import read_upload
from rover_common import (
    analyze_image_bytes,
    check_stream,
    grab_frame,
    parse_ip_port,
    stream_url,
)

router = APIRouter(prefix="/api/camera", tags=["Camera"])


@router.post("/connect", summary="Verify rover camera stream is reachable")
async def connect_camera(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    ip, port = parse_ip_port(payload)
    reachable = await check_stream(ip, port)

    if not reachable:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Could not reach the camera stream at {stream_url(ip, port)}. "
                "Check the rover Wi-Fi and the IP/port."
            ),
        )

    return {
        "success":    True,
        "ip":         ip,
        "port":       port,
        "stream_url": stream_url(ip, port),
        "message":    f"Camera connected at {ip}:{port}",
    }


@router.post("/capture", summary="Capture a frame from MJPEG stream and analyse")
async def capture_from_stream(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip, port = parse_ip_port(payload)
    parcel_id = payload.get("parcel_id")
    latitude  = payload.get("latitude")
    longitude = payload.get("longitude")

    image_bytes = await grab_frame(ip, port)
    return await analyze_image_bytes(
        image_bytes, db, current_user, source="camera",
        parcel_id=parcel_id, latitude=latitude, longitude=longitude,
        lang=request_lang(request),
    )


@router.post("/analyze-frame", summary="Analyse a browser-captured JPEG frame")
async def analyze_frame(
    request: Request,
    file: UploadFile = File(...),
    parcel_id: Optional[int]   = Form(None),
    latitude:  Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image_bytes = await read_upload(file)
    return await analyze_image_bytes(
        image_bytes, db, current_user, source="camera",
        parcel_id=parcel_id, latitude=latitude, longitude=longitude,
        lang=request_lang(request),
    )


@router.post("/upload", summary="Upload an image file for disease analysis")
async def upload_and_analyze(
    request: Request,
    file: UploadFile = File(...),
    parcel_id: Optional[int]   = Form(None),
    latitude:  Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image_bytes = await read_upload(file)
    return await analyze_image_bytes(
        image_bytes, db, current_user, source="upload",
        parcel_id=parcel_id, latitude=latitude, longitude=longitude,
        lang=request_lang(request),
    )
