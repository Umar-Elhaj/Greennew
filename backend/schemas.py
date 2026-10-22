# ============================================================
# GREEN App — Pydantic Schemas
# Request/response data validation for FastAPI endpoints.
# These define what JSON the API accepts and returns.
# ============================================================

from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from datetime import datetime
import re


# =============================================================
# AUTH SCHEMAS
# =============================================================

MIN_PASSWORD_LENGTH = 8
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _clean_email(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip().lower()
    if not v:
        return None
    if len(v) > 255 or not EMAIL_RE.match(v):
        raise ValueError("Invalid email address.")
    return v


def _required_text(v: str) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError("This field cannot be empty.")
    return v


class UserRegister(BaseModel):
    """Data required to create a new account."""
    first_name:   str
    last_name:    str
    phone:        str           # Primary identifier (required)
    email:        Optional[str] = None
    password:     str
    company_name: Optional[str] = None
    region:       Optional[str] = None
    dataset_consent: bool = False   # explicit opt-in, unchecked by default

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Strips spaces and validates basic phone format."""
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not re.match(r"^\+?[0-9]{8,15}$", cleaned):
            raise ValueError("Invalid phone number format.")
        return cleaned

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_names(cls, v: str) -> str:
        return _required_text(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        return _clean_email(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        return v


class UserLogin(BaseModel):
    """Data required to log in (phone or email + password)."""
    identifier: str   # Accepts phone number OR email address
    password:   str


class UserUpdate(BaseModel):
    """Fields the user can update on their profile."""
    first_name:   Optional[str] = None
    last_name:    Optional[str] = None
    email:        Optional[str] = None
    company_name: Optional[str] = None
    region:       Optional[str] = None
    avatar_url:   Optional[str] = None
    # Consents (Green Data dataset reuse, GPS read from photo metadata)
    dataset_consent:  Optional[bool] = None
    location_consent: Optional[bool] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_names(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _required_text(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        # "" clears the email (handled in the router), anything else must be valid
        return "" if v is not None and not v.strip() else _clean_email(v)


class PasswordChange(BaseModel):
    """For changing password from the profile settings."""
    current_password: str
    new_password:     str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"New password must be at least {MIN_PASSWORD_LENGTH} characters.")
        return v


# =============================================================
# RESPONSE SCHEMAS
# =============================================================

class UserResponse(BaseModel):
    """Public user data returned by the API (no password)."""
    id:           int
    first_name:   str
    last_name:    str
    phone:        str
    email:        Optional[str]
    company_name: Optional[str]
    region:       Optional[str]
    avatar_url:   Optional[str]
    is_active:    bool
    role:         str = "farmer"
    dataset_consent:  bool = False
    location_consent: bool = False
    created_at:   datetime

    model_config = {"from_attributes": True}  # Pydantic v2: allow ORM objects


class TokenResponse(BaseModel):
    """Returned after successful login or registration."""
    access_token: str
    token_type:   str = "bearer"  # noqa: S105 (OAuth2 token type, not a secret)
    user:         UserResponse


class MessageResponse(BaseModel):
    """Generic success/info message response."""
    message: str
    success: bool = True


# =============================================================
# PARCEL SCHEMAS
# =============================================================

class ParcelCreate(BaseModel):
    name:        str
    crop_type:   Optional[str] = None
    area_ha:     Optional[float] = None
    region:      Optional[str] = None
    description: Optional[str] = None
    geometry:    Optional[Any] = None   # GeoJSON polygon
    latitude:    Optional[float] = None
    longitude:   Optional[float] = None


class ParcelResponse(BaseModel):
    id:          int
    name:        str
    crop_type:   Optional[str]
    area_ha:     Optional[float]
    region:      Optional[str]
    description: Optional[str]
    geometry:    Optional[Any]
    latitude:    Optional[float]
    longitude:   Optional[float]
    is_active:   bool
    created_at:  datetime

    model_config = {"from_attributes": True}


# =============================================================
# DISEASE ANALYSIS SCHEMAS
# =============================================================

class AnalysisResponse(BaseModel):
    id:               int
    source:           str
    detected_disease: Optional[str]
    disease_name:     Optional[str]
    confidence:       Optional[float]
    severity:         Optional[str]
    plant_type:       Optional[str]
    latitude:         Optional[float]
    longitude:        Optional[float]
    fiche_terrain:    Optional[Any]
    notes:            Optional[str]
    created_at:       datetime
    parcel_id:        Optional[int]

    model_config = {"from_attributes": True}


# =============================================================
# CHATBOT SCHEMAS
# =============================================================

class ChatSessionResponse(BaseModel):
    id:         int
    title:      Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    content:     str
    analysis_id: Optional[int] = None  # Link message to a disease analysis


class ChatMessageResponse(BaseModel):
    id:          int
    role:        str
    content:     str
    created_at:  datetime

    model_config = {"from_attributes": True}


class ChatSessionDetail(BaseModel):
    id:         int
    title:      Optional[str]
    messages:   List[ChatMessageResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
