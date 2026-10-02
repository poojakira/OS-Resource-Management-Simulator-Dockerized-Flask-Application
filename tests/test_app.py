import pytest

from app import RESOURCE_NAMES, create_app


@pytest.fixture()
def client():
    application = create_app()
    application.config.update(TESTING=True)
    with application.test_client() as test_client:
        yield test_client


def test_index_lists_all_resources(client):
    response = client.get("/")

    assert response.status_code == 200
    for resource in RESOURCE_NAMES:
        assert resource.encode() in response.data


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_allocate_and_release_resource(client):
    allocate = client.post("/resource/Stove/allocate")
    assert allocate.status_code == 303

    allocated_page = client.get("/")
    assert b"Stove" in allocated_page.data
    assert b"Occupied" in allocated_page.data

    release = client.post("/resource/Stove/release")
    assert release.status_code == 303

    released_page = client.get("/")
    assert b"Stove" in released_page.data
    assert b"Available" in released_page.data


def test_unknown_resource_returns_404(client):
    assert client.post("/resource/Unknown/allocate").status_code == 404
    assert client.post("/resource/Unknown/release").status_code == 404


def test_get_cannot_mutate_resource_state(client):
    assert client.get("/resource/Stove/allocate").status_code == 405
    assert client.get("/resource/Stove/release").status_code == 405


def test_reset_restores_all_resources(client):
    client.post("/resource/Stove/allocate")
    client.post("/resource/Oven/allocate")

    response = client.post("/reset")
    assert response.status_code == 303

    state = client.application.config["RESOURCE_STATE"]
    assert all(status == "Available" for status in state.values())


def test_security_headers_are_present(client):
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
