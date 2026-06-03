"""Tests for the generation flow: /generate → /jobs/{id} → /plan."""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from lighting_engine.brief.models import LightingLayer, RoomBrief, Zone


@pytest.fixture
def stub_brief() -> RoomBrief:
    """A minimal RoomBrief the mocked generator returns for pipeline tests."""
    return RoomBrief(
        target_lux_ambient=180.0,
        cct_main=2700,
        fixture_preference="warm-bias",
        layers_needed=[LightingLayer.ambient],
        zones=[
            Zone(
                layer=LightingLayer.ambient,
                purpose="ambient over center",
                cct_k=2700, cri_min=90,
                fixture_type="downlight",
                position_hint="center",
            ),
        ],
        warnings=[],
        design_rationale="Warm 2700K ambient downlights for a cozy living room.",
        design_notes=["Keep uplight if a TV wall is present."],
        floor_lamp_suggestions=[],
        table_lamp_suggestions=[],
    )


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


def _poll_until_done(client: TestClient, job_id: str, timeout_s: float = 8.0) -> str:
    """Block until the job reaches a terminal state, returning the final status."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] in ("done", "failed"):
            # Surface the error message in the assertion message when failed,
            # so debugging doesn't require a second test run.
            if body["status"] == "failed":
                error_resp = client.get(f"/api/jobs/{job_id}")
                return f"failed: {error_resp.json().get('error')!r}"
            return body["status"]
        time.sleep(0.05)
    return "timeout"


def test_job_status_progresses_to_done(
    client: TestClient, seeded_project: dict[str, str], stub_brief: RoomBrief,
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    _confirm_room_basics(client, pid, rid)
    # Mock the LLM call so the test doesn't depend on an Anthropic API key.
    with patch(
        "lighting_engine.api._generation_pipeline.generate_room_brief",
        return_value=stub_brief,
    ):
        create = client.post(f"/api/projects/{pid}/rooms/{rid}/generate")
        job_id: str = create.json()["job_id"]
        final_status = _poll_until_done(client, job_id)

    assert final_status == "done", f"job did not finish: {final_status}"

    # The terminal status response should include a result_url.
    resp = client.get(f"/api/jobs/{job_id}")
    body = resp.json()
    assert body["result_url"] == f"/api/projects/{pid}/rooms/{rid}/plan"


def test_plan_returns_real_payload(
    client: TestClient, seeded_project: dict[str, str], stub_brief: RoomBrief,
) -> None:
    """End-to-end: real pipeline produces non-empty SVGs, non-zero lux,
    a fixture schedule, and the brief's design rationale text."""
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    _confirm_room_basics(client, pid, rid)
    with patch(
        "lighting_engine.api._generation_pipeline.generate_room_brief",
        return_value=stub_brief,
    ):
        create = client.post(f"/api/projects/{pid}/rooms/{rid}/generate")
        job_id: str = create.json()["job_id"]
        final = _poll_until_done(client, job_id)
        assert final == "done", final

    resp = client.get(f"/api/projects/{pid}/rooms/{rid}/plan")
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["project_id"] == pid
    assert plan["room_id"] == rid
    # SVGs are non-empty and well-formed
    assert plan["rcp_svg"].startswith("<svg")
    assert plan["rcp_svg"].rstrip().endswith("</svg>")
    assert plan["furniture_svg"].startswith("<svg")
    # The brief's rationale text propagates to the report
    assert "2700K" in plan["design_rationale"]
    # The deterministic placement put at least one ambient downlight
    assert len(plan["fixture_schedule"]) >= 1
    # Lux stats are real numbers, not zeros (one ambient grid produces > 0 mean)
    assert plan["lux_uniformity"]["mean_lux"] > 0
    # Metadata records the model used and a generated_at timestamp
    assert plan["metadata"]["model_used"] == "claude-opus-4-7"
    assert "generated_at" in plan["metadata"]


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
