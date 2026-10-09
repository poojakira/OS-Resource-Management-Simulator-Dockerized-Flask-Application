from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .models import audit_events, idempotency_records, leases, resources

RESOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class ResourceService:
    def __init__(self, engine: Engine, default_ttl: int, max_ttl: int) -> None:
        self.engine = engine
        self.default_ttl = default_ttl
        self.max_ttl = max_ttl

    def _audit(
        self,
        conn,
        event_type: str,
        actor: str,
        resource_id: str | None = None,
        lease_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            sa.insert(audit_events).values(
                id=str(uuid4()),
                event_type=event_type,
                resource_id=resource_id,
                lease_id=lease_id,
                actor=actor,
                detail_json=json.dumps(detail or {}, sort_keys=True),
                created_at=utcnow(),
            )
        )

    def ttl(self, value: Any) -> int:
        if value is None:
            return self.default_ttl
        if isinstance(value, bool) or not isinstance(value, int):
            raise ServiceError(400, "invalid_ttl", "ttl_seconds must be an integer")
        if value < 30 or value > self.max_ttl:
            raise ServiceError(400, "invalid_ttl", "ttl_seconds is outside the allowed range")
        return value

    def _expire_if_needed(self, conn, resource: dict[str, Any]) -> dict[str, Any]:
        lease_id = resource.get("active_lease_id")
        if not lease_id:
            return resource
        lease = conn.execute(sa.select(leases).where(leases.c.id == lease_id)).mappings().first()
        if lease is None:
            conn.execute(
                sa.update(resources)
                .where(resources.c.id == resource["id"])
                .where(resources.c.active_lease_id == lease_id)
                .values(active_lease_id=None)
            )
            return {**resource, "active_lease_id": None}
        if lease["status"] == "active" and aware(lease["expires_at"]) <= utcnow():
            now = utcnow()
            conn.execute(
                sa.update(leases)
                .where(leases.c.id == lease_id)
                .values(status="expired", released_at=now)
            )
            conn.execute(
                sa.update(resources)
                .where(resources.c.id == resource["id"])
                .where(resources.c.active_lease_id == lease_id)
                .values(active_lease_id=None)
            )
            self._audit(
                conn,
                "lease.expired",
                "system",
                resource_id=resource["id"],
                lease_id=lease_id,
            )
            return {**resource, "active_lease_id": None}
        return resource

    @staticmethod
    def lease_payload(lease: dict[str, Any]) -> dict[str, Any]:
        def iso(value: datetime | None) -> str | None:
            return aware(value).isoformat() if value else None

        return {
            "id": lease["id"],
            "resource_id": lease["resource_id"],
            "owner": lease["owner"],
            "purpose": lease["purpose"],
            "status": lease["status"],
            "acquired_at": iso(lease["acquired_at"]),
            "expires_at": iso(lease["expires_at"]),
            "released_at": iso(lease["released_at"]),
            "fencing_token": lease["fencing_token"],
        }

    def resource_payload(self, conn, resource: dict[str, Any]) -> dict[str, Any]:
        active = None
        if resource.get("active_lease_id"):
            lease = (
                conn.execute(sa.select(leases).where(leases.c.id == resource["active_lease_id"]))
                .mappings()
                .first()
            )
            if lease:
                active = self.lease_payload(dict(lease))
        return {
            "id": resource["id"],
            "name": resource["name"],
            "kind": resource["kind"],
            "metadata": json.loads(resource["metadata_json"] or "{}"),
            "available": active is None,
            "fencing_token": resource["fencing_token"],
            "active_lease": active,
        }

    def create_resource(
        self,
        resource_id: str,
        name: str,
        kind: str,
        metadata_value: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        resource_id = resource_id.strip().lower()
        if not RESOURCE_ID_RE.fullmatch(resource_id):
            raise ServiceError(400, "invalid_resource_id", "resource id must be a lowercase slug")
        if not name.strip() or not kind.strip():
            raise ServiceError(400, "invalid_resource", "name and kind are required")
        with self.engine.begin() as conn:
            if conn.execute(sa.select(resources.c.id).where(resources.c.id == resource_id)).first():
                raise ServiceError(409, "resource_exists", "resource already exists")
            conn.execute(
                sa.insert(resources).values(
                    id=resource_id,
                    name=name.strip()[:128],
                    kind=kind.strip()[:64],
                    metadata_json=json.dumps(metadata_value, sort_keys=True),
                    active_lease_id=None,
                    fencing_token=0,
                    created_at=utcnow(),
                    deleted_at=None,
                )
            )
            self._audit(conn, "resource.created", actor, resource_id=resource_id)
        return self.get_resource(resource_id)

    def get_resource(self, resource_id: str) -> dict[str, Any]:
        with self.engine.begin() as conn:
            row = (
                conn.execute(
                    sa.select(resources).where(
                        resources.c.id == resource_id,
                        resources.c.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise ServiceError(404, "resource_not_found", "resource not found")
            resource = self._expire_if_needed(conn, dict(row))
            return self.resource_payload(conn, resource)

    def list_resources(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        with self.engine.begin() as conn:
            rows = (
                conn.execute(
                    sa.select(resources)
                    .where(resources.c.deleted_at.is_(None))
                    .order_by(resources.c.id)
                )
                .mappings()
                .all()
            )
            for row in rows:
                resource = self._expire_if_needed(conn, dict(row))
                result.append(self.resource_payload(conn, resource))
        return result

    def acquire(
        self,
        resource_id: str,
        owner: str,
        purpose: str,
        ttl_value: Any,
        actor: str,
        idempotency_key: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if not owner.strip():
            raise ServiceError(400, "invalid_owner", "owner is required")
        ttl = self.ttl(ttl_value)
        request_body = {
            "resource_id": resource_id,
            "owner": owner.strip(),
            "purpose": purpose.strip(),
            "ttl_seconds": ttl,
            "actor": actor,
        }
        request_hash = hashlib.sha256(
            json.dumps(request_body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        record_key = None
        if idempotency_key:
            if len(idempotency_key) > 128:
                raise ServiceError(
                    400,
                    "invalid_idempotency_key",
                    "idempotency key is too long",
                )
            record_key = hashlib.sha256(f"{actor}:{idempotency_key}".encode()).hexdigest()

        with self.engine.begin() as conn:
            if record_key:
                cached = (
                    conn.execute(
                        sa.select(idempotency_records).where(
                            idempotency_records.c.idempotency_key == record_key
                        )
                    )
                    .mappings()
                    .first()
                )
                if cached:
                    if cached["request_hash"] != request_hash:
                        raise ServiceError(
                            409,
                            "idempotency_conflict",
                            "idempotency key was already used with a different request",
                        )
                    if cached["status_code"] == 0:
                        raise ServiceError(
                            409,
                            "idempotency_in_progress",
                            "an identical request is still being processed",
                        )
                    return json.loads(cached["response_json"]), True

                try:
                    with conn.begin_nested():
                        conn.execute(
                            sa.insert(idempotency_records).values(
                                idempotency_key=record_key,
                                request_hash=request_hash,
                                status_code=0,
                                response_json="",
                                created_at=utcnow(),
                            )
                        )
                except IntegrityError:
                    cached = (
                        conn.execute(
                            sa.select(idempotency_records).where(
                                idempotency_records.c.idempotency_key == record_key
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if cached is None:
                        raise ServiceError(
                            409,
                            "idempotency_in_progress",
                            "an identical request is still being processed",
                        ) from None
                    if cached["request_hash"] != request_hash:
                        raise ServiceError(
                            409,
                            "idempotency_conflict",
                            "idempotency key was already used with a different request",
                        ) from None
                    if cached["status_code"] == 0:
                        raise ServiceError(
                            409,
                            "idempotency_in_progress",
                            "an identical request is still being processed",
                        ) from None
                    return json.loads(cached["response_json"]), True

            row = (
                conn.execute(
                    sa.select(resources).where(
                        resources.c.id == resource_id,
                        resources.c.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise ServiceError(404, "resource_not_found", "resource not found")
            resource = self._expire_if_needed(conn, dict(row))
            if resource.get("active_lease_id"):
                raise ServiceError(409, "resource_busy", "resource already has an active lease")

            now = utcnow()
            lease_id = str(uuid4())
            claimed = conn.execute(
                sa.update(resources)
                .where(resources.c.id == resource_id)
                .where(resources.c.deleted_at.is_(None))
                .where(resources.c.active_lease_id.is_(None))
                .values(
                    active_lease_id=lease_id,
                    fencing_token=resources.c.fencing_token + 1,
                )
            )
            if claimed.rowcount != 1:
                raise ServiceError(409, "resource_busy", "resource was acquired concurrently")

            fencing_token = conn.execute(
                sa.select(resources.c.fencing_token).where(resources.c.id == resource_id)
            ).scalar_one()

            conn.execute(
                sa.insert(leases).values(
                    id=lease_id,
                    resource_id=resource_id,
                    owner=owner.strip()[:128],
                    purpose=purpose.strip()[:512],
                    status="active",
                    acquired_at=now,
                    expires_at=now + timedelta(seconds=ttl),
                    released_at=None,
                    fencing_token=fencing_token,
                )
            )
            self._audit(
                conn,
                "lease.acquired",
                actor,
                resource_id=resource_id,
                lease_id=lease_id,
                detail={
                    "owner": owner.strip(),
                    "ttl_seconds": ttl,
                    "fencing_token": fencing_token,
                },
            )
            lease = conn.execute(sa.select(leases).where(leases.c.id == lease_id)).mappings().one()
            response = self.lease_payload(dict(lease))
            if record_key:
                conn.execute(
                    sa.update(idempotency_records)
                    .where(idempotency_records.c.idempotency_key == record_key)
                    .values(
                        status_code=201,
                        response_json=json.dumps(
                            response,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    )
                )
            return response, False

    def release(self, lease_id: str, actor: str) -> dict[str, Any]:
        with self.engine.begin() as conn:
            lease = (
                conn.execute(sa.select(leases).where(leases.c.id == lease_id)).mappings().first()
            )
            if lease is None:
                raise ServiceError(404, "lease_not_found", "lease not found")
            if lease["status"] != "active":
                return self.lease_payload(dict(lease))
            now = utcnow()
            conn.execute(
                sa.update(leases)
                .where(leases.c.id == lease_id)
                .values(status="released", released_at=now)
            )
            conn.execute(
                sa.update(resources)
                .where(resources.c.id == lease["resource_id"])
                .where(resources.c.active_lease_id == lease_id)
                .values(active_lease_id=None)
            )
            self._audit(
                conn,
                "lease.released",
                actor,
                resource_id=lease["resource_id"],
                lease_id=lease_id,
            )
            updated = (
                conn.execute(sa.select(leases).where(leases.c.id == lease_id)).mappings().one()
            )
            return self.lease_payload(dict(updated))

    def renew(self, lease_id: str, ttl_value: Any, actor: str) -> dict[str, Any]:
        ttl = self.ttl(ttl_value)
        with self.engine.begin() as conn:
            lease = (
                conn.execute(sa.select(leases).where(leases.c.id == lease_id)).mappings().first()
            )
            if lease is None:
                raise ServiceError(404, "lease_not_found", "lease not found")
            if lease["status"] != "active":
                raise ServiceError(409, "lease_not_active", "only active leases can be renewed")
            now = utcnow()
            if aware(lease["expires_at"]) <= now:
                conn.execute(
                    sa.update(leases)
                    .where(leases.c.id == lease_id)
                    .values(status="expired", released_at=now)
                )
                conn.execute(
                    sa.update(resources)
                    .where(resources.c.id == lease["resource_id"])
                    .where(resources.c.active_lease_id == lease_id)
                    .values(active_lease_id=None)
                )
                self._audit(
                    conn,
                    "lease.expired",
                    "system",
                    resource_id=lease["resource_id"],
                    lease_id=lease_id,
                )
                raise ServiceError(409, "lease_expired", "expired leases cannot be renewed")
            conn.execute(
                sa.update(leases)
                .where(leases.c.id == lease_id)
                .values(expires_at=now + timedelta(seconds=ttl))
            )
            self._audit(
                conn,
                "lease.renewed",
                actor,
                resource_id=lease["resource_id"],
                lease_id=lease_id,
                detail={"ttl_seconds": ttl},
            )
            updated = (
                conn.execute(sa.select(leases).where(leases.c.id == lease_id)).mappings().one()
            )
            return self.lease_payload(dict(updated))

    def list_leases(self, status: str | None, owner: str | None) -> list[dict[str, Any]]:
        statement = sa.select(leases).order_by(leases.c.acquired_at.desc()).limit(500)
        if status:
            statement = statement.where(leases.c.status == status)
        if owner:
            statement = statement.where(leases.c.owner == owner)
        with self.engine.connect() as conn:
            return [self.lease_payload(dict(row)) for row in conn.execute(statement).mappings()]

    def audit(self, limit: int) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self.engine.connect() as conn:
            rows = conn.execute(
                sa.select(audit_events).order_by(audit_events.c.created_at.desc()).limit(limit)
            ).mappings()
            return [
                {
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "resource_id": row["resource_id"],
                    "lease_id": row["lease_id"],
                    "actor": row["actor"],
                    "detail": json.loads(row["detail_json"] or "{}"),
                    "created_at": aware(row["created_at"]).isoformat(),
                }
                for row in rows
            ]

    def active_count(self) -> int:
        with self.engine.connect() as conn:
            return int(
                conn.execute(
                    sa.select(sa.func.count())
                    .select_from(leases)
                    .where(
                        leases.c.status == "active",
                        leases.c.expires_at > utcnow(),
                    )
                ).scalar_one()
            )

    def remove_resource(self, resource_id: str, actor: str) -> None:
        with self.engine.begin() as conn:
            row = (
                conn.execute(
                    sa.select(resources).where(
                        resources.c.id == resource_id,
                        resources.c.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise ServiceError(404, "resource_not_found", "resource not found")
            row = self._expire_if_needed(conn, dict(row))
            if row.get("active_lease_id"):
                raise ServiceError(409, "resource_busy", "release the active lease first")
            now = utcnow()
            self._audit(conn, "resource.deleted", actor, resource_id=resource_id)
            conn.execute(
                sa.update(resources).where(resources.c.id == resource_id).values(deleted_at=now)
            )
