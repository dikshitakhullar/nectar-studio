"""Smoke tests: the app boots, health check works, OpenAPI renders."""

from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "lighting-engine"
    assert body["version"]


def test_openapi_schema(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "nectar-studio lighting engine"

    paths = schema.get("paths", {})
    # Spot-check that the critical contract endpoints are wired up.
    assert "/api/projects" in paths
    assert "/api/projects/{project_id}/rooms" in paths
    assert "/api/projects/{project_id}/rooms/{room_id}" in paths
    assert "/api/projects/{project_id}/rooms/{room_id}/walls" in paths
    assert "/api/projects/{project_id}/rooms/{room_id}/furniture" in paths
    assert "/api/projects/{project_id}/rooms/{room_id}/brief" in paths
    assert "/api/projects/{project_id}/rooms/{room_id}/generate" in paths
    assert "/api/projects/{project_id}/rooms/{room_id}/plan" in paths
    assert "/api/jobs/{job_id}" in paths


def test_docs_render(client: TestClient) -> None:
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower()


def test_cors_includes_localhost(client: TestClient) -> None:
    resp = client.options(
        "/healthz",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # 200 with allow-origin header indicates CORS preflight succeeded.
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
