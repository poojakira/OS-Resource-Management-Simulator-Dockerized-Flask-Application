from __future__ import annotations

import pytest

from resource_control import create_app


@pytest.fixture()
def app(tmp_path):
    database = tmp_path / "control.db"
    return create_app(
        {
            "TESTING": True,
            "AUTO_CREATE_SCHEMA": True,
            "DATABASE_URL": f"sqlite:///{database}",
            "RESOURCE_API_KEYS": (
                "reader:reader:reader-key-0000000000000000,"
                "operator:operator:operator-key-0000000000000,"
                "admin:admin:admin-key-000000000000000000"
            ),
            "DEFAULT_LEASE_TTL_SECONDS": 300,
            "MAX_LEASE_TTL_SECONDS": 3600,
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def reader_headers():
    return {"Authorization": "Bearer reader-key-0000000000000000"}


@pytest.fixture()
def operator_headers():
    return {"Authorization": "Bearer operator-key-0000000000000"}


@pytest.fixture()
def admin_headers():
    return {"Authorization": "Bearer admin-key-000000000000000000"}


def create_resource(client, headers, resource_id="gpu-a"):
    return client.post(
        "/api/v1/resources",
        headers=headers,
        json={
            "id": resource_id,
            "name": "GPU Node A",
            "kind": "gpu",
            "metadata": {"zone": "lab"},
        },
    )


def test_health_and_readiness_are_public(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_api_and_metrics_require_auth(client):
    assert client.get("/api/v1/resources").status_code == 401
    assert client.get("/metrics").status_code == 401


def test_role_boundaries(client, reader_headers, operator_headers, admin_headers):
    denied = client.post(
        "/api/v1/resources",
        headers=reader_headers,
        json={"id": "gpu-a", "name": "GPU", "kind": "gpu"},
    )
    assert denied.status_code == 403

    created = create_resource(client, admin_headers)
    assert created.status_code == 201

    acquire = client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=operator_headers,
        json={"owner": "team-a", "purpose": "benchmark", "ttl_seconds": 300},
    )
    assert acquire.status_code == 201

    assert client.get("/api/v1/audit", headers=reader_headers).status_code == 403
    assert client.get("/api/v1/audit", headers=admin_headers).status_code == 200


def test_acquire_conflict_release_and_reacquire(client, admin_headers, operator_headers):
    create_resource(client, admin_headers)

    first = client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=operator_headers,
        json={"owner": "team-a", "purpose": "benchmark", "ttl_seconds": 300},
    )
    assert first.status_code == 201
    lease_id = first.get_json()["id"]

    conflict = client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=operator_headers,
        json={"owner": "team-b", "purpose": "second job", "ttl_seconds": 300},
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error"]["code"] == "resource_busy"

    released = client.delete(f"/api/v1/leases/{lease_id}", headers=operator_headers)
    assert released.status_code == 200
    assert released.get_json()["status"] == "released"

    second = client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=operator_headers,
        json={"owner": "team-b", "purpose": "second job", "ttl_seconds": 300},
    )
    assert second.status_code == 201


def test_acquire_is_idempotent(client, admin_headers, operator_headers):
    create_resource(client, admin_headers)
    headers = {**operator_headers, "Idempotency-Key": "job-123"}
    body = {"owner": "team-a", "purpose": "benchmark", "ttl_seconds": 300}

    first = client.post("/api/v1/resources/gpu-a/leases", headers=headers, json=body)
    replay = client.post("/api/v1/resources/gpu-a/leases", headers=headers, json=body)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.get_json()["id"] == first.get_json()["id"]


def test_idempotency_key_rejects_different_request(client, admin_headers, operator_headers):
    create_resource(client, admin_headers)
    headers = {**operator_headers, "Idempotency-Key": "job-123"}

    client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=headers,
        json={"owner": "team-a", "purpose": "one", "ttl_seconds": 300},
    )
    response = client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=headers,
        json={"owner": "team-a", "purpose": "two", "ttl_seconds": 300},
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "idempotency_conflict"


def test_renew_active_lease(client, admin_headers, operator_headers):
    create_resource(client, admin_headers)
    acquired = client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=operator_headers,
        json={"owner": "team-a", "purpose": "run", "ttl_seconds": 300},
    )
    response = client.post(
        f"/api/v1/leases/{acquired.get_json()['id']}/renew",
        headers=operator_headers,
        json={"ttl_seconds": 600},
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "active"


def test_invalid_ttl_and_mutating_get_are_rejected(
    client, admin_headers, operator_headers
):
    create_resource(client, admin_headers)

    invalid = client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=operator_headers,
        json={"owner": "team-a", "purpose": "run", "ttl_seconds": 1},
    )
    assert invalid.status_code == 400
    assert client.get(
        "/api/v1/resources/gpu-a/leases", headers=operator_headers
    ).status_code == 405


def test_metrics_and_security_headers(client, reader_headers):
    metrics = client.get("/metrics", headers=reader_headers)
    assert metrics.status_code == 200
    assert b"resource_control_http_requests_total" in metrics.data

    response = client.get("/healthz", headers={"X-Request-ID": "trace-123"})
    assert response.headers["X-Request-ID"] == "trace-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_resource_delete_requires_idle_resource(
    client, admin_headers, operator_headers
):
    create_resource(client, admin_headers)
    acquired = client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=operator_headers,
        json={"owner": "team-a", "purpose": "run", "ttl_seconds": 300},
    )
    assert client.delete("/api/v1/resources/gpu-a", headers=admin_headers).status_code == 409

    client.delete(
        f"/api/v1/leases/{acquired.get_json()['id']}",
        headers=operator_headers,
    )
    assert client.delete("/api/v1/resources/gpu-a", headers=admin_headers).status_code == 204


def test_audit_records_resource_and_lease_events(
    client, admin_headers, operator_headers
):
    create_resource(client, admin_headers)
    client.post(
        "/api/v1/resources/gpu-a/leases",
        headers=operator_headers,
        json={"owner": "team-a", "purpose": "run", "ttl_seconds": 300},
    )
    audit = client.get("/api/v1/audit", headers=admin_headers)
    event_types = {item["event_type"] for item in audit.get_json()["items"]}
    assert {"resource.created", "lease.acquired"} <= event_types
