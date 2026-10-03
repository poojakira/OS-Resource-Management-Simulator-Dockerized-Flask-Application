from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine

from resource_control.models import metadata
from resource_control.service import ResourceService, ServiceError

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL integration URL not set")
def test_postgres_concurrency_stress_has_single_active_holder():
    """Exercise the lease boundary under a burst of competing workers.

    This is a database-level concurrency stress test, not a distributed-consensus claim.
    """
    engine = create_engine(
        os.environ["TEST_DATABASE_URL"],
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=20,
    )
    metadata.drop_all(engine)
    metadata.create_all(engine)
    service = ResourceService(engine, default_ttl=300, max_ttl=3600)
    service.create_resource("gpu-shared-1", "Shared GPU", "gpu", {"zone": "ci"}, "ci-admin")

    def acquire(i: int):
        owner = f"worker-{i:02d}"
        try:
            lease, replayed = service.acquire(
                "gpu-shared-1",
                owner,
                "burst-concurrency-validation",
                300,
                owner,
                f"request-{i:02d}",
            )
            return ("ok", lease["id"], owner, replayed)
        except ServiceError as exc:
            return (exc.code, None, owner, False)

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(acquire, range(32)))

    winners = [row for row in results if row[0] == "ok"]
    busy = [row for row in results if row[0] == "resource_busy"]
    assert len(winners) == 1
    assert len(busy) == 31
    assert winners[0][3] is False


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL integration URL not set")
def test_concurrent_idempotent_retries_resolve_to_one_lease():
    """Concurrent retries of the same logical request must converge on one lease."""
    engine = create_engine(
        os.environ["TEST_DATABASE_URL"],
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=20,
    )
    metadata.drop_all(engine)
    metadata.create_all(engine)
    service = ResourceService(engine, default_ttl=300, max_ttl=3600)
    service.create_resource("gpu-idempotent-1", "Shared GPU", "gpu", {}, "ci-admin")

    def acquire(_: int):
        lease, replayed = service.acquire(
            "gpu-idempotent-1",
            "same-job",
            "idempotent-retry-validation",
            300,
            "same-job",
            "same-request-key",
        )
        return lease["id"], replayed

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(acquire, range(24)))

    lease_ids = {lease_id for lease_id, _ in results}
    assert len(lease_ids) == 1
    assert sum(1 for _, replayed in results if replayed is False) == 1
    assert sum(1 for _, replayed in results if replayed is True) == 23
