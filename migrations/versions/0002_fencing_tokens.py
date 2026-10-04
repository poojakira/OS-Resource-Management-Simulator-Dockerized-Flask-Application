"""add monotonic fencing tokens to resource leases

Revision ID: 0002_fencing_tokens
Revises: 0001_initial
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_fencing_tokens"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column(
            "fencing_token",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "leases",
        sa.Column(
            "fencing_token",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("leases", "fencing_token")
    op.drop_column("resources", "fencing_token")
