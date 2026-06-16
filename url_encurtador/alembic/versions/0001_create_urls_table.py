"""create urls table

Revision ID: 0001
Revises:
Create Date: 2026-06-16

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "urls",
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index("ix_urls_expires_at", "urls", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_urls_expires_at", table_name="urls")
    op.drop_table("urls")
