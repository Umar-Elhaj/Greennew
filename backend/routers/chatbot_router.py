# ============================================================
# GREEN App — GreenBot Router (Phase 6)
# RAG-powered agronomic chatbot using Google Gemini API.
#
# Endpoints:
#   POST /api/chat/sessions          — create a new session
#   GET  /api/chat/sessions          — list user's sessions
#   GET  /api/chat/sessions/{id}     — get session + messages
#   POST /api/chat/sessions/{id}/messages — send message, get reply
#   DELETE /api/chat/sessions/{id}   — delete session
# ============================================================

import json
import os
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import ChatSession, ChatMessage, DiseaseAnalysis, User
from auth import get_current_user
from config import GEMINI_API_KEY, GEMINI_MODEL, RAG_CHUNKS_PATH
from i18n import request_lang
from knowledge import class_code, class_name, fiche_for_analysis, plant_name
from models import Parcel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["GreenBot"])


# =============================================================
# RAG ENGINE — load chunks + TF-IDF index at startup
# =============================================================
_chunks: List[dict] = []
_vectorizer = None
_tfidf_matrix = None

def _load_rag():
    """Load RAG corpus and build TF-IDF index (called once at startup)."""
    global _chunks, _vectorizer, _tfidf_matrix

    if not os.path.exists(RAG_CHUNKS_PATH):
        logger.warning(f"[GreenBot] RAG chunks not found at {RAG_CHUNKS_PATH}")
        return

    with open(RAG_CHUNKS_PATH, encoding="utf-8") as f:
        _chunks = json.load(f)

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        texts = [c.get("text", "") for c in _chunks]
        _vectorizer = TfidfVectorizer(
            max_features=8000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            strip_accents="unicode",
        )
        _tfidf_matrix = _vectorizer.fit_transform(texts)
        logger.info(f"[GreenBot] RAG index built — {len(_chunks)} chunks, TF-IDF shape {_tfidf_matrix.shape}")
    except Exception as e:
        logger.error(f"[GreenBot] Failed to build TF-IDF index: {e}")
        _vectorizer = None
        _tfidf_matrix = None

# _load_rag() is NOT called at import time.
# It is triggered from main.py's lifespan in a background thread so the
# server starts accepting requests immediately.


def _retrieve_context(query: str, top_k: int = 5) -> str:
    """Return the top-k most relevant text chunks for a query."""
    if _vectorizer is None or _tfidf_matrix is None or not _chunks:
        _load_rag()
        
    if _vectorizer is None or _tfidf_matrix is None or not _chunks:
        return ""

    try:
        from sklearn.metrics.pairwise import cosine_similarity

        q_vec = _vectorizer.transform([query])
        scores = cosine_similarity(q_vec, _tfidf_matrix).flatten()
        top_indices = scores.argsort()[-top_k:][::-1]

        parts = []
        for idx in top_indices:
            if scores[idx] > 0.01:   # skip near-zero relevance
                chunk = _chunks[idx]
                parts.append(f"[Source: {chunk.get('source','?')} p.{chunk.get('page','?')}]\n{chunk.get('text','')}")
        return "\n\n---\n\n".join(parts)
    except Exception as e:
        logger.error(f"[GreenBot] RAG retrieval error: {e}")
        return ""


# =============================================================
# GOOGLE GEMINI API CLIENT
# =============================================================
_gemini_client = None
_gemini_client_key = None   # track key to detect changes


def _get_client():
    """
    Return a Google Gemini client.
    Re-creates the client if GEMINI_API_KEY changed since last call.
    """
    global _gemini_client, _gemini_client_key
    api_key = os.environ.get("GEMINI_API_KEY", "") or GEMINI_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="GreenBot is not configured on this server.",
        )
    if _gemini_client is None or _gemini_client_key != api_key:
        try:
            from google import genai
            _gemini_client     = genai.Client(api_key=api_key)
            _gemini_client_key = api_key
            logger.info("[GreenBot] Gemini client initialised.")
        except ImportError:
            logger.error("[GreenBot] google-genai is not installed")
            raise HTTPException(status_code=503, detail="GreenBot is not configured on this server.")
    return _gemini_client


SYSTEM_PROMPT = """You are GreenBot, the agronomic assistant of GREEN, an agricultural intelligence platform for farms in Cameroon and Central Africa. GREEN detects probable plant diseases (cassava, maize, tomato) from photos with an EfficientNet-B0 model, maps parcels and tracks analyses over time.

You help farmers, farm managers and field agronomists with:
- plant diseases and pests of Cameroonian crops, their symptoms and integrated management;
- treatments suited to the local context (availability of products, approved products, costs);
- sustainable practices, crop calendars and farm management;
- interpreting GREEN's analysis results.

Rules:
- {language_rule}
- Be precise, practical and actionable: short paragraphs, lists and clear steps.
- A GREEN result is a PROBABLE disease predicted by an AI model, never a certain diagnosis. Say so when you discuss it, and recommend confirming in the field (or with an agronomist) before any treatment, especially when the confidence is low.
- If an analysis is provided in the context, interpret it first. If you use the agronomic knowledge base excerpts, say so briefly.
- Recommend only pesticides approved for the crop, with protective equipment and the label's dose; prefer preventive and non-chemical measures first.
- Never give human medical diagnoses. If you are not sure, say so clearly.
"""

LANGUAGE_RULES = {
    "fr": "Answer in French (use 'vous'), the language of the user's interface, unless the user clearly writes in another language.",
    "en": "Answer in English, the language of the user's interface, unless the user clearly writes in another language.",
}


def _call_llm(messages: list, context_rag: str = "", analysis_context: str = "", lang: str = "en",
              user_context: str = "") -> str:
    """
    Call Google Gemini API with full conversation history.

    message format: [{"role": "user"|"assistant", "content": "..."}]
    The system prompt + RAG context are injected via system_instruction.
    """
    client = _get_client()

    # Build the system instruction with optional RAG and analysis context
    system = SYSTEM_PROMPT.format(language_rule=LANGUAGE_RULES.get(lang, LANGUAGE_RULES["en"]))
    if user_context:
        system += f"\n\n--- USER CONTEXT ---\n{user_context}\n--- END USER CONTEXT ---"
    if analysis_context:
        system += f"\n\n--- GREEN ANALYSIS BEING DISCUSSED ---\n{analysis_context}\n--- END ANALYSIS ---"
    if context_rag:
        system += (
            "\n\n--- AGRONOMIC KNOWLEDGE BASE (relevant excerpts) ---\n"
            f"{context_rag}\n--- END KNOWLEDGE BASE ---"
        )

    # Convert message history to Gemini format
    # Gemini uses "user" and "model" roles (not "assistant")
    gemini_contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })

    try:
        from google.genai import types

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=gemini_contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=1024,
                temperature=0.7,
            ),
        )
        return response.text

    except Exception as e:
        # Details go to the log only: provider errors may contain keys or internals.
        err_str = str(e)
        logger.error(f"[GreenBot] Gemini API error: {err_str}")

        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            raise HTTPException(
                status_code=429,
                detail="GreenBot is busy (usage quota reached). Please try again in a few minutes.",
            )
        if "403" in err_str or "PERMISSION_DENIED" in err_str or "API key" in err_str:
            raise HTTPException(status_code=503, detail="GreenBot is not configured on this server.")
        raise HTTPException(status_code=502, detail="GreenBot is temporarily unavailable. Please try again later.")


# =============================================================
# PYDANTIC SCHEMAS
# =============================================================
class SessionCreate(BaseModel):
    title: Optional[str] = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    analysis_id: Optional[int] = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    analysis_id: Optional[int]
    created_at: str

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: int
    title: Optional[str]
    created_at: str
    updated_at: str
    message_count: int = 0

    class Config:
        from_attributes = True


class SessionDetailOut(BaseModel):
    id: int
    title: Optional[str]
    created_at: str
    updated_at: str
    messages: List[MessageOut]

    class Config:
        from_attributes = True


# =============================================================
# HELPERS
# =============================================================
def _fmt(dt) -> str:
    return dt.isoformat() if dt else ""


def _owned_analysis(analysis_id: Optional[int], user: User, db: Session) -> Optional[DiseaseAnalysis]:
    """The analysis only if it belongs to the user (an id alone grants nothing)."""
    if not analysis_id:
        return None
    a = db.query(DiseaseAnalysis).filter(
        DiseaseAnalysis.id == analysis_id, DiseaseAnalysis.user_id == user.id,
    ).first()
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return a


def _analysis_context(a: Optional[DiseaseAnalysis], lang: str) -> str:
    """Structured context of one analysis for the LLM (always English labels; facts only)."""
    if a is None:
        return ""
    fiche = fiche_for_analysis(a, lang)
    code = class_code(a.detected_disease, a.plant_type)
    lines = [
        f"Analysis #{a.id} (source: {a.source}, date: {a.created_at:%Y-%m-%d})",
        f"Plant: {plant_name(a.plant_type, 'en')}",
        f"Model result: {class_name(code, 'en')} — "
        + ("healthy" if fiche['winner']['type'] == 'healthy' else "PROBABLE disease (AI prediction, not a diagnosis)"),
        f"Model confidence: {fiche['confidence']}%" + (" (LOW: result uncertain)" if fiche["low_confidence"] else ""),
    ]
    if len(fiche["top3"]) > 1:
        others = ", ".join(f"{class_name(t['code'], 'en')} {t['confidence']}%" for t in fiche["top3"][1:])
        lines.append(f"Other candidates: {others}")
    if fiche["symptoms"]:
        lines.append(f"Reference symptoms: {'; '.join(fiche['symptoms'][:4])}")
    if fiche["recommendations"]:
        lines.append(f"Reference actions: {'; '.join(fiche['recommendations'][:4])}")
    return "\n".join(lines)


def _user_context(user: User, db: Session) -> str:
    """Region and parcels of the user: lets GreenBot adapt advice to the farm."""
    parcels = db.query(Parcel).filter(Parcel.user_id == user.id, Parcel.is_active == True).limit(10).all()  # noqa: E712
    lines = [f"Region of Cameroon: {user.region or 'unknown'}"]
    if parcels:
        lines.append("Parcels: " + "; ".join(
            f"{p.name} ({p.crop_type or 'crop not set'}{f', {p.area_ha:.2f} ha' if p.area_ha else ''})" for p in parcels))
    return "\n".join(lines)


def _auto_title(content: str) -> str:
    """Generate a short session title from the first message."""
    words = content.strip().split()
    title = " ".join(words[:8])
    if len(words) > 8:
        title += "…"
    return title[:80]


# =============================================================
# ENDPOINTS
# =============================================================

@router.post("/sessions", status_code=201)
async def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new GreenBot chat session."""
    try:
        session = ChatSession(
            user_id=current_user.id,
            title=payload.title or "New conversation",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return {
            "id": session.id,
            "title": session.title,
            "created_at": _fmt(session.created_at),
            "updated_at": _fmt(session.updated_at),
            "message_count": 0,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"[GreenBot] Failed to create session for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Could not create the conversation. Please try again.")


@router.get("/sessions")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all sessions for the current user (newest first)."""
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": _fmt(s.created_at),
            "updated_at": _fmt(s.updated_at),
            "message_count": len(s.messages),
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a session with all its messages."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Explicit query — bypasses ORM relationship cache so we always
    # get the latest committed messages even right after a write.
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    return {
        "id": session.id,
        "title": session.title,
        "created_at": _fmt(session.created_at),
        "updated_at": _fmt(session.updated_at),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "analysis_id": m.analysis_id,
                "created_at": _fmt(m.created_at),
            }
            for m in messages
        ],
    }


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int,
    payload: MessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a user message and receive GreenBot's reply.
    Performs RAG retrieval and calls the Gemini model (GEMINI_MODEL), answering
    in the request language.
    """
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    from models import utcnow

    analysis = _owned_analysis(payload.analysis_id, current_user, db)

    # Load prior messages via explicit query (bypasses ORM cache)
    prior_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    # Auto-title the session from the first user message
    if not prior_msgs:
        session.title = _auto_title(payload.content)

    # ── Commit user message first (separate transaction) ──────────────────
    # This guarantees the user's message is always saved even if Gemini
    # later fails (quota 429, network error) — nothing will roll it back.
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=payload.content,
        analysis_id=payload.analysis_id,
    )
    db.add(user_msg)
    session.updated_at = utcnow()
    db.commit()
    db.refresh(user_msg)

    # Build history: prior messages + the just-committed user message
    history = [{"role": m.role, "content": m.content} for m in prior_msgs[-19:]]
    history.append({"role": "user", "content": payload.content})

    # RAG: retrieve relevant agricultural knowledge
    rag_context = _retrieve_context(payload.content, top_k=5)

    # Optional: enrich with the linked analysis (owned by the user) and the farm
    analysis_ctx = _analysis_context(analysis, request_lang(request))

    # ── Call Gemini (may raise HTTPException — user msg already saved) ────
    reply_text = _call_llm(history, rag_context, analysis_ctx, request_lang(request),
                           _user_context(current_user, db))

    # ── Commit assistant reply ────────────────────────────────────────────
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=reply_text,
    )
    db.add(assistant_msg)
    session.updated_at = utcnow()
    db.commit()
    db.refresh(assistant_msg)

    return {
        "id": assistant_msg.id,
        "role": "assistant",
        "content": reply_text,
        "created_at": _fmt(assistant_msg.created_at),
        "session_title": session.title,
        "rag_used": bool(rag_context),
    }


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a session and all its messages."""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    db.delete(session)
    db.commit()
