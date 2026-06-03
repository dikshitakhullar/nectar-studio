"""Tests for the generation flow: /generate → /jobs/{id} → /plan."""

import time

from fastapi.testclient import TestClient


def _confirm_room_basics(
    client: TestClient, pid: str, rid: str,
) -> None:
    """Set the required-by-generate fields so /generate doesn't 400."""
    resp = client.post(
        f"/api/projects/{pid}/rooms/{rid}",
        json={
            "ceiling_height_m": 3.0,
            "type_confirmed": "living",
            "main_window_orientation": "S",
        },
    )
    assert resp.status_code == 200, resp.text


def test_generate_returns_job_id(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    _confirm_room_basics(client, pid, rid)
    resp = client.post(f"/api/projects/{pid}/rooms/{rid}/generate")
    assert resp.status_code == 202, resp.text
    assert "job_id" in resp.json()


def test_generate_missing_fields_returns_400(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    # Skip the basics POST → required fields are missing.
    resp = client.post(f"/api/projects/{pid}/rooms/{rid}/generate")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "missing_fields" in detail
    assert "ceiling_height_m" in detail["missing_fields"]
    assert "main_window_orientation" in detail["missing_fields"]


def test_job_status_progresses_to_done(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    _confirm_room_basics(client, pid, rid)
    create = client.post(f"/api/projects/{pid}/rooms/{rid}/generate")
    job_id: str = create.json()["job_id"]

    # Poll. With STUB_GENERATION_SLEEP_SECONDS=0.05 (set by the fixture) the
    # job should reach `done` well within the loop budget here.
    deadline = time.monotonic() + 5.0
    final_status: str = "pending"
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        final_status = resp.json()["status"]
        if final_status in ("done", "failed"):
            break
        time.sleep(0.05)

    assert final_status == "done", f"job did not finish: {final_status}"

    # The terminal status response should include a result_url.
    resp = client.get(f"/api/jobs/{job_id}")
    body = resp.json()
    assert body["result_url"] == f"/api/projects/{pid}/rooms/{rid}/plan"


def test_plan_returns_stub_payload(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    _confirm_room_basics(client, pid, rid)
    create = client.post(f"/api/projects/{pid}/rooms/{rid}/generate")
    job_id: str = create.json()["job_id"]

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        if resp.json()["status"] == "done":
            break
        time.sleep(0.05)

    resp = client.get(f"/api/projects/{pid}/rooms/{rid}/plan")
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["project_id"] == pid
    assert plan["room_id"] == rid
    assert plan["rcp_svg"] == ""
    assert plan["furniture_svg"] == ""
    # Stub warning must surface so studio can show a "draft only" banner.
    assert any("stub" in w for w in plan["warnings"])
    assert plan["lux_uniformity"]["meets_target"] is False


def test_plan_404_when_no_job_done(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    resp = client.get(f"/api/projects/{pid}/rooms/{rid}/plan")
    assert resp.status_code == 404


def test_unknown_job_404(client: TestClient) -> None:
    resp = client.get("/api/jobs/nope")
    assert resp.status_code == 404
