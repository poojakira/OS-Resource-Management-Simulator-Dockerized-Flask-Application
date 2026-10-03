from __future__ import annotations

from resource_control import create_app


def test_home_page_is_public_and_describes_control_plane(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "AUTO_CREATE_SCHEMA": True,
            "DATABASE_URL": f"sqlite:///{tmp_path / 'home.db'}",
            "RESOURCE_API_KEYS": "admin:admin:admin-key-000000000000000000",
            "RATE_LIMIT_PER_MINUTE": 1000,
        }
    )
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert b"Resource Control Plane" in response.data
