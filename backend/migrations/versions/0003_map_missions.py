"""GREEN Map: parcel measures and offline id, missions, analysis cell (additive)

Revision ID: 0003_map_missions
Revises: 0002_media_and_roles
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa

# JSONB/DOUBLE/DATETIME(6)/MEDIUMTEXT per dialect (backend/db_types.py)
from db_types import DateTimeType, FloatType, JSONType, MYSQL_TABLE_OPTIONS

revision = "0003_map_missions"
down_revision = "0002_media_and_roles"
branch_labels = None
depends_on = None


def _is_pg() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _now():
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        return sa.text("(now() at time zone 'utc')")
    if dialect == "mysql":
        # DATETIME(6) needs a default of the same precision; the session
        # time zone is UTC (db_url.engine_kwargs)
        return sa.text("CURRENT_TIMESTAMP(6)")
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    with op.batch_alter_table("parcels") as b:
        b.add_column(sa.Column("perimeter_m", FloatType))
        b.add_column(sa.Column("sowing_date", sa.Date()))
        b.add_column(sa.Column("client_id", sa.String(36)))
        b.create_unique_constraint("uq_parcels_user_client_id", ["user_id", "client_id"])

    op.create_table(
        "missions",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parcel_id", sa.Integer(), sa.ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("cell_size_m", FloatType, nullable=False),
        sa.Column("speed_mps", FloatType, nullable=False, server_default=sa.text("0.5")),
        sa.Column("start_lat", FloatType),
        sa.Column("start_lng", FloatType),
        sa.Column("angle_deg", FloatType),
        sa.Column("cells_total", sa.Integer(), nullable=False),
        sa.Column("distance_m", FloatType, nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("grid", JSONType, nullable=False),
        sa.Column("waypoints", JSONType, nullable=False),
        sa.Column("created_at", DateTimeType, nullable=False, server_default=_now()),
        sa.Column("updated_at", DateTimeType, nullable=False, server_default=_now()),
        sa.CheckConstraint("status in ('draft', 'ready', 'running', 'done')", name="missions_status_check"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("ix_missions_user_id", "missions", ["user_id"])
    op.create_index("ix_missions_parcel_id", "missions", ["parcel_id"])
    if _is_pg():
        op.execute("alter table public.missions enable row level security")

    with op.batch_alter_table("disease_analyses") as b:
        b.add_column(sa.Column("mission_id", sa.Integer()))
        b.add_column(sa.Column("cell_index", sa.Integer()))
        b.add_column(sa.Column("captured_at", DateTimeType))
        b.create_foreign_key("disease_analyses_mission_id_fkey", "missions", ["mission_id"], ["id"],
                             ondelete="SET NULL")
    op.create_index("ix_disease_analyses_mission_cell", "disease_analyses", ["mission_id", "cell_index"])


def downgrade() -> None:
    # Development only: never run on production data.
    op.drop_index("ix_disease_analyses_mission_cell", table_name="disease_analyses")
    with op.batch_alter_table("disease_analyses") as b:
        b.drop_constraint("disease_analyses_mission_id_fkey", type_="foreignkey")
        b.drop_column("captured_at")
        b.drop_column("cell_index")
        b.drop_column("mission_id")
    op.drop_index("ix_missions_parcel_id", table_name="missions")
    op.drop_index("ix_missions_user_id", table_name="missions")
    op.drop_table("missions")
    with op.batch_alter_table("parcels") as b:
        b.drop_constraint("uq_parcels_user_client_id", type_="unique")
        b.drop_column("client_id")
        b.drop_column("sowing_date")
        b.drop_column("perimeter_m")
