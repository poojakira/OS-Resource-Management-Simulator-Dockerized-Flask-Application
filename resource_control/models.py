from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text

metadata = MetaData()

resources = Table(
    "resources",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(128), nullable=False),
    Column("kind", String(64), nullable=False),
    Column("metadata_json", Text, nullable=False, default="{}"),
    Column("active_lease_id", String(36), nullable=True, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True, index=True),
)

leases = Table(
    "leases",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "resource_id",
        String(64),
        ForeignKey("resources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    Column("owner", String(128), nullable=False, index=True),
    Column("purpose", String(512), nullable=False, default=""),
    Column("status", String(16), nullable=False, index=True),
    Column("acquired_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("released_at", DateTime(timezone=True), nullable=True),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("event_type", String(32), nullable=False, index=True),
    Column("resource_id", String(64), nullable=True, index=True),
    Column("lease_id", String(36), nullable=True, index=True),
    Column("actor", String(128), nullable=False),
    Column("detail_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

idempotency_records = Table(
    "idempotency_records",
    metadata,
    Column("idempotency_key", String(160), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("status_code", Integer, nullable=False),
    Column("response_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
