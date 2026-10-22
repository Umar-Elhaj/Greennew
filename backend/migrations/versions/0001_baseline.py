"""baseline: schema as deployed on Supabase before Alembic (commit 36d4768)

On a database created from backend/sql/supabase_schema.sql (or by the old
create_all), do NOT run this revision: mark it as applied instead with
    alembic stamp 0001_baseline
then `alembic upgrade head` applies only the additive revisions.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

TABLES = ("users", "parcels", "disease_analyses", "chat_sessions", "chat_messages")


def _is_pg() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _now():
    return sa.text("(now() at time zone 'utc')") if _is_pg() else sa.text("CURRENT_TIMESTAMP")


def _json():
    return JSONB() if _is_pg() else sa.JSON()


def _id():
    return sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True)


def _timestamps(updated=True):
    cols = [sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now())]
    if updated:
        cols.append(sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=_now()))
    return cols


def upgrade() -> None:
    op.create_table(
        "users",
        _id(),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("email", sa.String(255), unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255)),
        sa.Column("region", sa.String(100)),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("dataset_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
    )

    op.create_table(
        "parcels",
        _id(),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("crop_type", sa.String(100)),
        sa.Column("area_ha", sa.Float()),
        sa.Column("region", sa.String(100)),
        sa.Column("description", sa.Text()),
        sa.Column("geometry", _json()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
    )
    op.create_index("ix_parcels_user_id", "parcels", ["user_id"])

    op.create_table(
        "disease_analyses",
        _id(),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parcel_id", sa.Integer(), sa.ForeignKey("parcels.id", ondelete="CASCADE")),
        sa.Column("source", sa.String(50), server_default="camera"),
        sa.Column("image_path", sa.String(500)),
        sa.Column("image_sha256", sa.CHAR(64)),
        sa.Column("detected_disease", sa.String(255)),
        sa.Column("disease_name", sa.String(255)),
        sa.Column("confidence", sa.Float()),
        sa.Column("severity", sa.String(50)),
        sa.Column("plant_type", sa.String(100)),
        sa.Column("predictions", _json()),
        sa.Column("model_version", sa.String(100)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("fiche_terrain", _json()),
        sa.Column("notes", sa.Text()),
        sa.Column("consent_dataset", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified_label", sa.String(255)),
        sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime()),
        *_timestamps(updated=False),
        sa.CheckConstraint("confidence between 0 and 1", name="disease_analyses_confidence_check"),
    )
    op.create_index("ix_disease_analyses_user_id", "disease_analyses", ["user_id"])
    op.create_index("ix_disease_analyses_parcel_id", "disease_analyses", ["parcel_id"])
    op.create_index("ix_disease_analyses_created_at", "disease_analyses", ["created_at"])
    op.create_index("ix_disease_analyses_sha256", "disease_analyses", ["image_sha256"])
    where = sa.text("consent_dataset and image_path is not null")
    op.create_index(
        "ix_disease_analyses_dataset", "disease_analyses", ["plant_type", "detected_disease"],
        postgresql_where=where, sqlite_where=where,
    )

    op.create_table(
        "chat_sessions",
        _id(),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255)),
        *_timestamps(),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])

    op.create_table(
        "chat_messages",
        _id(),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("disease_analyses.id", ondelete="SET NULL")),
        *_timestamps(updated=False),
        sa.CheckConstraint("role in ('user', 'assistant')", name="chat_messages_role_check"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    # Supabase exposes every public table through its REST API (anon key).
    # RLS without any policy blocks that API; the backend connects as the
    # table owner and is not affected.
    if _is_pg():
        for t in TABLES:
            op.execute(f"alter table public.{t} enable row level security")


def downgrade() -> None:
    # Dropping every table is never what a downgrade of the baseline should do.
    raise NotImplementedError("The baseline cannot be downgraded.")
