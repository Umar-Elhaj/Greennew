"""GREEN Data: demo flag and aggregate index (additive)

Revision ID: 0004_green_data
Revises: 0003_map_missions
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_green_data"
down_revision = "0003_map_missions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("disease_analyses") as b:
        b.add_column(sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_index("ix_disease_analyses_green_data", "disease_analyses", ["consent_dataset", "is_demo", "created_at"])


def downgrade() -> None:
    # Development only: never run on production data.
    op.drop_index("ix_disease_analyses_green_data", table_name="disease_analyses")
    with op.batch_alter_table("disease_analyses") as b:
        b.drop_column("is_demo")
