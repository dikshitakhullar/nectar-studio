"""End-to-end test for POST /api/projects with a real DXF fixture."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "dwgs"
    / "real_base_architectural.dxf"
)


@pytest.mark.skipif(not _FIXTURE.exists(), reason="Delhi fixture not present")
def test_post_project_returns_project_id_and_rooms(client: TestClient) -> None:
    with _FIXTURE.open("rb") as fh:
        resp = client.post(
            "/api/projects",
            files={"ceiling": ("ceiling.dxf", fh, "application/dxf")},
            data={"project_name": "Test Delhi", "location": "delhi"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "project_id" in body
    assert isinstance(body["rooms"], list)
    # Delhi fixture should yield at least one first-class room.
    assert len(body["rooms"]) > 0
    for room in body["rooms"]:
        assert {"id", "name", "type", "dims", "polygon", "tier"}.issubset(room.keys())
        assert room["tier"] in {"first_class", "generic"}


@pytest.mark.skipif(not _FIXTURE.exists(), reason="Delhi fixture not present")
def test_get_rooms_after_upload(client: TestClient) -> None:
    with _FIXTURE.open("rb") as fh:
        create = client.post(
            "/api/projects",
            files={"ceiling": ("ceiling.dxf", fh, "application/dxf")},
            data={"project_name": "Test Delhi"},
        )
    assert create.status_code == 201, create.text
    pid: str = create.json()["project_id"]

    resp = client.get(f"/api/projects/{pid}/rooms")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["rooms"], list)
    assert len(body["rooms"]) == len(create.json()["rooms"])


def test_get_rooms_unknown_project_404(client: TestClient) -> None:
    resp = client.get("/api/projects/does-not-exist/rooms")
    assert resp.status_code == 404


def test_post_project_with_furniture_optional(client: TestClient) -> None:
    if not _FIXTURE.exists():
        pytest.skip("Delhi fixture not present")
    with _FIXTURE.open("rb") as fh:
        # Furniture file is omitted intentionally — Phase 2 only requires ceiling.
        resp = client.post(
            "/api/projects",
            files={"ceiling": ("ceiling.dxf", fh, "application/dxf")},
        )
    assert resp.status_code == 201, resp.text
