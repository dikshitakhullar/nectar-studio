"""Tests for the clarification endpoints (basics / walls / furniture / brief)."""

from fastapi.testclient import TestClient


def test_get_room_returns_confirmed_blob(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    resp = client.get(f"/api/projects/{pid}/rooms/{rid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == rid
    assert body["type_inferred"] == "living"
    assert body["type_confirmed"] is None
    assert "provenance" in body
    assert body["provenance"]["polygon_inferred"] == "parser"


def test_get_room_unknown_404(client: TestClient) -> None:
    resp = client.get("/api/projects/nope/rooms/also-nope")
    assert resp.status_code == 404


def test_post_basics_merges_clarifications(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    resp = client.post(
        f"/api/projects/{pid}/rooms/{rid}",
        json={
            "ceiling_height_m": 3.0,
            "type_confirmed": "living",
            "main_window_orientation": "N",
            "ceiling_type": "flat",
            "occupants": ["adult", "kids"],
            "floor_finish": "mid",
            "wall_finish": "light",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ceiling_height_m"] == 3.0
    assert body["type_confirmed"] == "living"
    assert body["main_window_orientation"] == "N"
    # Provenance flips to "user" for everything the request touched.
    assert body["provenance"]["ceiling_height_m"] == "user"
    assert body["provenance"]["main_window_orientation"] == "user"
    # Parser-sourced fields stay "parser".
    assert body["provenance"]["polygon_inferred"] == "parser"


def test_walls_default_one_per_polygon_edge(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    resp = client.get(f"/api/projects/{pid}/rooms/{rid}/walls")
    assert resp.status_code == 200
    walls = resp.json()["walls"]
    # Seeded room has a 4-vertex polygon → 4 default walls.
    assert len(walls) == 4
    for i, w in enumerate(walls):
        assert w["index"] == i
        assert w["confirm"] is False


def test_post_wall_persists_confirmation(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    resp = client.post(
        f"/api/projects/{pid}/rooms/{rid}/walls/0",
        json={
            "index": 0,
            "confirm": True,
            "doors_confirmed": [],
            "windows_confirmed": [],
            "notes": "south-facing window wall",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["walls"][0]["confirm"] is True
    assert body["walls"][0]["notes"] == "south-facing window wall"
    assert body["provenance"]["walls[0]"] == "user"


def test_post_furniture_merges_notes_and_mood(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    resp = client.post(
        f"/api/projects/{pid}/rooms/{rid}/furniture",
        json={
            "furniture_notes": "L-sofa anchored to N wall",
            "mood": "cozy",
            "activities": ["reading", "movies"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["furniture_notes"] == "L-sofa anchored to N wall"
    assert body["intent_mood"] == "cozy"
    assert body["activities"] == ["reading", "movies"]


def test_post_brief_sets_time_of_use(
    client: TestClient, seeded_project: dict[str, str],
) -> None:
    pid = seeded_project["project_id"]
    rid = seeded_project["room_id"]
    resp = client.post(
        f"/api/projects/{pid}/rooms/{rid}/brief",
        json={
            "intent_mood": "wind_down",
            "activities": ["reading"],
            "time_of_use": ["evening", "late_night"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent_mood"] == "wind_down"
    assert body["time_of_use"] == ["evening", "late_night"]
    assert body["provenance"]["time_of_use"] == "user"
