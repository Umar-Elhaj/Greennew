# ============================================================
# GREEN App — Camera / Rover Router (MVP)
#
#   POST /api/camera/analyze-frame  → analyse a frame captured in the browser
#   POST /api/camera/upload         → analyse an imported image file
#   POST /api/camera/connect        → (local development only) check that the
#   POST /api/camera/capture           server can reach the rover's MJPEG stream
#                                       and grab a frame. A hosted server cannot
#                                       reach the rover's private IP: production
#                                       uses analyze-frame (store-and-forward).
# ============================================================

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from auth import get_current_user
from config import DEBUG
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


def dev_only():
    """/connect and /capture make the server fetch any IP:port: local development only."""
    if not DEBUG:
        raise HTTPException(status_code=404, detail="Not Found")


@router.post("/connect", summary="Verify rover camera stream is reachable (DEBUG only)",
             dependencies=[Depends(dev_only)])
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


@router.post("/capture", summary="Capture a frame from MJPEG stream and analyse (DEBUG only)",
             dependencies=[Depends(dev_only)])
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


@router.post("/analyze-frame", summary="Analyse a frame captured in the browser (device camera or rover stream)")
async def analyze_frame(
    request: Request,
    file: UploadFile = File(...),
    source:    str             = Form("camera", pattern="^(camera|rover)$"),
    parcel_id: Optional[int]   = Form(None),
    latitude:  Optional[float] = Form(None, ge=-90, le=90),
    longitude: Optional[float] = Form(None, ge=-180, le=180),
    mission_id:  Optional[int]      = Form(None),
    cell_index:  Optional[int]      = Form(None, ge=1),
    captured_at: Optional[datetime] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image_bytes = await read_upload(file)
    return await analyze_image_bytes(
        image_bytes, db, current_user, source=source,
        parcel_id=parcel_id, latitude=latitude, longitude=longitude,
        lang=request_lang(request),
        mission_id=mission_id, cell_index=cell_index, captured_at=captured_at,
    )


@router.post("/upload", summary="Upload an image file for disease analysis")
async def upload_and_analyze(
    request: Request,
    file: UploadFile = File(...),
    parcel_id: Optional[int]   = Form(None),
    latitude:  Optional[float] = Form(None, ge=-90, le=90),
    longitude: Optional[float] = Form(None, ge=-180, le=180),
    mission_id:  Optional[int]      = Form(None),
    cell_index:  Optional[int]      = Form(None, ge=1),
    captured_at: Optional[datetime] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image_bytes = await read_upload(file)
    return await analyze_image_bytes(
        image_bytes, db, current_user, source="upload",
        parcel_id=parcel_id, latitude=latitude, longitude=longitude,
        lang=request_lang(request),
        mission_id=mission_id, cell_index=cell_index, captured_at=captured_at,
    )
