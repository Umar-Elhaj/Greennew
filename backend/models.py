# ============================================================
# GREEN App — Database Models (SQLAlchemy ORM)
# Each class maps to a table (SQLite in dev, PostgreSQL/Supabase in prod).
# Schema changes go through Alembic (backend/migrations); the
# test_migrations test fails if models and migrations diverge.
# backend/sql/supabase_schema.sql mirrors the final state for reference.
# ============================================================

from sqlalchemy import (
    CHAR, JSON, Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey,
    Identity, Index, Integer, String, Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base
import datetime

# jsonb on PostgreSQL (indexable, compact), plain JSON elsewhere
JSONType = JSON().with_variant(JSONB(), "postgresql")


# ---- Helper -------------------------------------------------
def utcnow():
    """Returns current UTC time (used as default for timestamps)."""
    return datetime.datetime.utcnow()


# =============================================================
# USER — Platform accounts (enterprise managers / agronomists)
# =============================================================
class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, Identity(), primary_key=True)
    first_name    = Column(String(100), nullable=False)
    last_name     = Column(String(100), nullable=False)
    phone         = Column(String(20),  unique=True, nullable=False)
    email         = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    company_name  = Column(String(255), nullable=True)   # Agribusiness name
    region        = Column(String(100), nullable=True)   # Cameroon region
    avatar_url    = Column(String(500), nullable=True)
    is_active     = Column(Boolean, default=True, nullable=False)
    dataset_consent = Column(Boolean, default=False, nullable=False)  # Green Data opt-in
    # Keep the GPS position found in uploaded photos (EXIF); off by default
    location_consent = Column(Boolean, default=False, nullable=False)
    # farmer | agronomist (verifies analyses) | partner (GREEN Data) | admin
    role          = Column(String(20), default="farmer", nullable=False)
    created_at    = Column(DateTime, default=utcnow, nullable=False)
    updated_at    = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("role in ('farmer', 'agronomist', 'partner', 'admin')", name="users_role_check"),
    )

    # Relationships
    parcels          = relationship("Parcel",          back_populates="owner", cascade="all, delete-orphan")
    analyses         = relationship("DiseaseAnalysis", back_populates="user",  cascade="all, delete-orphan",
                                    foreign_keys="DiseaseAnalysis.user_id")
    chat_sessions    = relationship("ChatSession",     back_populates="user",  cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} phone={self.phone}>"


# =============================================================
# PARCEL — Agricultural land plots / parcelles
# =============================================================
class Parcel(Base):
    __tablename__ = "parcels"

    id          = Column(Integer, Identity(), primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = Column(String(255), nullable=False)         # e.g. "Parcelle Nord-Est"
    crop_type   = Column(String(100), nullable=True)          # e.g. "Maïs", "Manioc", "Tomate"
    area_ha     = Column(Float, nullable=True)                # Area in hectares
    region      = Column(String(100), nullable=True)          # Cameroon region
    description = Column(Text, nullable=True)
    # GeoJSON polygon stored as JSON string (Leaflet.js compatible)
    geometry    = Column(JSONType, nullable=True)
    # Center coordinates for map display
    latitude    = Column(Float, nullable=True)
    longitude   = Column(Float, nullable=True)
    is_active   = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime, default=utcnow, nullable=False)
    updated_at  = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    owner    = relationship("User",            back_populates="parcels")
    analyses = relationship("DiseaseAnalysis", back_populates="parcel", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Parcel id={self.id} name={self.name}>"


# =============================================================
# DISEASE ANALYSIS — Each drone scan / manual image analysis
# =============================================================
class DiseaseAnalysis(Base):
    __tablename__ = "disease_analyses"

    id              = Column(Integer, Identity(), primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id",   ondelete="CASCADE"), nullable=False, index=True)
    parcel_id       = Column(Integer, ForeignKey("parcels.id", ondelete="CASCADE"), nullable=True,  index=True)

    # Detection input
    source          = Column(String(50), default="camera")  # "camera" | "upload" | "drone"
    image_path      = Column(String(500), nullable=True)   # Relative path inside MEDIA_DIR
    image_sha256    = Column(CHAR(64),    nullable=True)   # Duplicate detection (indexed below)
    image_bytes     = Column(Integer, nullable=True)       # Size of the stored JPEG
    image_width     = Column(Integer, nullable=True)
    image_height    = Column(Integer, nullable=True)

    # Detection output — Disease model (EfficientNet)
    detected_disease= Column(String(255), nullable=True)   # Disease class ID or "healthy"
    disease_name    = Column(String(255), nullable=True)   # Human-readable name
    confidence      = Column(Float, nullable=True)         # 0.0 – 1.0
    severity        = Column(String(50),  nullable=True)   # "low" | "medium" | "high"
    plant_type      = Column(String(100), nullable=True)   # "tomate" | "maïs" | "manioc" etc.
    predictions     = Column(JSONType, nullable=True)      # Top-3 [{class, confidence}]
    model_version   = Column(String(100), nullable=True)

    # GPS coordinates (optional — rover GPS not yet implemented)
    latitude        = Column(Float, nullable=True)
    longitude       = Column(Float, nullable=True)

    # Generated terrain sheet (fiche terrain) stored as JSON
    fiche_terrain   = Column(JSONType, nullable=True)

    # Analysis metadata
    notes           = Column(Text, nullable=True)

    # Green Data — human validation + consent
    consent_dataset = Column(Boolean, default=False, nullable=False)
    verified_label  = Column(String(255), nullable=True)   # Class corrected by an agronomist
    verified_by     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at     = Column(DateTime, nullable=True)

    created_at      = Column(DateTime, default=utcnow, nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("confidence between 0 and 1", name="disease_analyses_confidence_check"),
        Index("ix_disease_analyses_sha256", "image_sha256"),
        # Dataset export: consented analyses that have an image
        Index(
            "ix_disease_analyses_dataset", "plant_type", "detected_disease",
            postgresql_where=text("consent_dataset and image_path is not null"),
            sqlite_where=text("consent_dataset and image_path is not null"),
        ),
    )

    # Relationships
    user   = relationship("User",   back_populates="analyses", foreign_keys=[user_id])
    parcel = relationship("Parcel", back_populates="analyses")

    def __repr__(self):
        return f"<DiseaseAnalysis id={self.id} disease={self.detected_disease} confidence={self.confidence}>"


# =============================================================
# CHAT SESSION — GreenBot conversation sessions
# =============================================================
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id         = Column(Integer, Identity(), primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title      = Column(String(255), nullable=True)   # Auto-generated from first message
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    user     = relationship("User",        back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at")

    def __repr__(self):
        return f"<ChatSession id={self.id} user_id={self.user_id}>"


# =============================================================
# CHAT MESSAGE — Individual messages within a GreenBot session
# =============================================================
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id         = Column(Integer, Identity(), primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role       = Column(String(20), nullable=False)   # "user" | "assistant"
    content    = Column(Text, nullable=False)
    # Optional: link message to a disease analysis for context
    analysis_id= Column(Integer, ForeignKey("disease_analyses.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')", name="chat_messages_role_check"),
    )

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage id={self.id} role={self.role}>"
