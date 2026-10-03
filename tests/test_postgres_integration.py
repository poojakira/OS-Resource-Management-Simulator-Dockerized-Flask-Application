from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine

from resource_control.models import metadata
from resource_control.service import ResourceService, ServiceError

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL integration URL not set")
def test_postgres_atomic_single_winner():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    metadata.drop_all(engine)
    metadata.create_all(engine)
    service = ResourceService(engine, default_ttl=300, max_ttl=3600)
    service.create_resource("lab-device-1", "Lab Device 1", "device", {}, "ci-admin")

    def acquire(owner: str):
        try:
            lease, _ = service.acquire(
                "lab-device-1",
                owner,
                "concurrency test",
                300,
                owner,
                None,
            )
            return ("ok", lease["owner"])
        except ServiceError as exc:
            return (exc.code, owner)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(acquire, ["ci-a", "ci-b"]))

    assert sum(1 for result, _ in results if result == "ok") == 1
    assert sum(1 for result, _ in results if result == "resource_busy") == 1
