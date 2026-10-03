"""initial production schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("active_lease_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_resources_active_lease_id", "resources", ["active_lease_id"])
    op.create_index("ix_resources_deleted_at", "resources", ["deleted_at"])

    op.create_table(
        "leases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "resource_id",
            sa.String(length=64),
            sa.ForeignKey("resources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_leases_resource_id", "leases", ["resource_id"])
    op.create_index("ix_leases_owner", "leases", ["owner"])
    op.create_index("ix_leases_status", "leases", ["status"])
    op.create_index("ix_leases_expires_at", "leases", ["expires_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("lease_id", sa.String(length=36), nullable=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])
    op.create_index("ix_audit_events_lease_id", "audit_events", ["lease_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    op.create_table(
        "idempotency_records",
        sa.Column("idempotency_key", sa.String(length=160), primary_key=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("audit_events")
    op.drop_table("leases")
    op.drop_table("resources")
