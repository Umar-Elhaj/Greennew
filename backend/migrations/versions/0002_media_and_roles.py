"""media metadata, user role and location consent (additive)

Revision ID: 0002_media_and_roles
Revises: 0001_baseline
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_media_and_roles"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("location_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        b.add_column(sa.Column("role", sa.String(20), nullable=False, server_default="farmer"))
        b.create_check_constraint("users_role_check", "role in ('farmer', 'agronomist', 'partner', 'admin')")

    with op.batch_alter_table("disease_analyses") as b:
        b.add_column(sa.Column("image_bytes", sa.Integer()))
        b.add_column(sa.Column("image_width", sa.Integer()))
        b.add_column(sa.Column("image_height", sa.Integer()))


def downgrade() -> None:
    # Development only: never run on production data.
    with op.batch_alter_table("disease_analyses") as b:
        b.drop_column("image_height")
        b.drop_column("image_width")
        b.drop_column("image_bytes")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("users_role_check", type_="check")
        b.drop_column("role")
        b.drop_column("location_consent")
