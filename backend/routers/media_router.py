# ============================================================
# GREEN App — Authenticated access to analysed images
#
#   GET /api/media/{yyyy}/{mm}/{uuid}[_thumb].jpg
#       Authorization: Bearer <jwt>       (API clients, scripts)
#    or ?u=<user_id>&exp=<ts>&sig=<hmac>  (URLs returned by the API, for <img>)
#
# Allowed: the owner of the analysis, an agronomist (verification) or an
# admin. 401 without valid credentials, 403 for anyone else.
# ============================================================

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from auth import user_from_request
from database import get_db
from media import MEDIA_PATH_RE, media_file, verify_signed
from models import DiseaseAnalysis, User

router = APIRouter(prefix="/api/media", tags=["Media"])

PRIVILEGED_ROLES = {"agronomist", "admin"}


def _requester(request: Request, path: str, db: Session,
               u: Optional[int], exp: Optional[int], sig: Optional[str]) -> User:
    if u is not None and exp is not None and sig:
        if not verify_signed(path, u, exp, sig):
            raise HTTPException(status_code=401, detail="Expired or invalid image link.")
        user = db.get(User, u)
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Expired or invalid image link.")
        return user
    user = user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


@router.get("/{path:path}", summary="Read a stored analysis image (owner, agronomist or admin)")
def get_media(
    path: str,
    request: Request,
    u: Optional[int] = None,
    exp: Optional[int] = None,
    sig: Optional[str] = None,
    db: Session = Depends(get_db),
):
    m = MEDIA_PATH_RE.match(path)
    if not m:  # also rejects "../", absolute paths, other extensions
        raise HTTPException(status_code=404, detail="Not found.")

    user = _requester(request, path, db, u, exp, sig)

    original = f"{m.group(1)}.jpg"
    analysis = db.query(DiseaseAnalysis).filter(DiseaseAnalysis.image_path == original).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Not found.")
    if analysis.user_id != user.id and (user.role or "farmer") not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="You do not have access to this image.")

    filepath = media_file(path)
    if (filepath is None or not os.path.exists(filepath)) and m.group(2):
        filepath = media_file(original)  # images stored before thumbnails existed
    if filepath is None or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Not found.")

    return FileResponse(
        filepath,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )
