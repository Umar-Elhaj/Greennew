# ============================================================
# GREEN App — Disease Database Router
#
# Serves the bilingual diseases.json reference database.
# No authentication required — public agronomic reference data.
# Entries are returned in the request language (?lang= / Accept-Language);
# search matches both languages, aliases and former ids.
#
#   GET /api/diseases        — list (optional ?q=, ?plant=, ?category=)
#   GET /api/diseases/{id}   — one entry by id or alias
# ============================================================

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from i18n import request_lang
from knowledge import get_entry, localize, search

router = APIRouter(prefix="/api/diseases", tags=["Disease Database"])


@router.get("", summary="List the reference diseases and pests")
def list_diseases(
    request: Request,
    q:        Optional[str] = Query(None, description="Search by name (FR or EN), alias, scientific name or plant"),
    plant:    Optional[str] = Query(None, description="Filter by affected plant (FR or EN)"),
    category: Optional[str] = Query(None, pattern="^(disease|pest|healthy)$"),
):
    return search(q=q, plant=plant, category=category, lang=request_lang(request))


@router.get("/{disease_id}", summary="Get one entry by id or alias")
def get_disease(disease_id: str, request: Request):
    entry = get_entry(disease_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Disease '{disease_id}' not found.")
    return localize(entry, request_lang(request))
