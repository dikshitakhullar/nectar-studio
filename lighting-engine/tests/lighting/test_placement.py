from pathlib import Path

from lighting_engine.digest import compute_digest
from lighting_engine.lighting import compute_ambient_layer
from lighting_engine.lighting.placement import place_ambient_for_project
from lighting_engine.models.geometry import (
    FixtureSource,
    LightingLayer,
    Point,
    Project,
    Room,
    RoomType,
)
from lighting_engine.parser.pipeline import parse_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


def _room(name: str, room_type: RoomType, side: float = 4.0) -> Room:
    s = side / 2
    return Room(
        id=name.lower().replace(" ", "-"),
        name=name,
        type=room_type,
        floor_level=0,
        polygon=[
            Point(x=-s, y=-s),
            Point(x=s, y=-s),
            Point(x=s, y=s),
            Point(x=-s, y=s),
        ],
        ceiling_height_m=2.7,
    )


def test_ambient_layer_places_fixtures_in_a_living_room():
    room = _room("Living", RoomType.living, side=5.0)
    project = Project(id="p", name="x", rooms=[room])
    digest = compute_digest(project).rooms[0]
    fixtures = compute_ambient_layer(room, digest)
    assert len(fixtures) >= 4   # 25 sqm × 150 lux should give multiple downlights
    for f in fixtures:
        assert f.source == FixtureSource.proposed
        assert f.layer == LightingLayer.ambient
        assert f.cct_k == 2700        # warm CCT for living
        assert f.lumens == 1200.0
        assert "Living" in f.reasoning or "living" in f.reasoning


def test_kitchen_gets_cool_cct():
    room = _room("Kitchen", RoomType.kitchen, side=5.0)
    project = Project(id="p", name="x", rooms=[room])
    digest = compute_digest(project).rooms[0]
    fixtures = compute_ambient_layer(room, digest)
    assert all(f.cct_k == 4000 for f in fixtures)


def test_outdoor_rooms_skip_placement():
    room = _room("Courtyard", RoomType.outdoor, side=5.0)
    project = Project(id="p", name="x", rooms=[room])
    digest = compute_digest(project).rooms[0]
    fixtures = compute_ambient_layer(room, digest)
    assert fixtures == []


def test_staircases_skip_ambient_placement():
    room = _room("Staircase", RoomType.staircase, side=3.0)
    project = Project(id="p", name="x", rooms=[room])
    digest = compute_digest(project).rooms[0]
    fixtures = compute_ambient_layer(room, digest)
    assert fixtures == []


def test_place_ambient_for_real_delhi_file():
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf", project_name="Mohak",
    )
    digest = compute_digest(project)
    by_room = place_ambient_for_project(project.rooms, digest.rooms)

    # Every interior room with a positive lux target should get at least one fixture
    interior_rooms = [
        r for r in project.rooms
        if r.type not in (RoomType.outdoor, RoomType.staircase) and r.area_sqm > 1.0
    ]
    for r in interior_rooms:
        assert len(by_room.get(r.id, [])) >= 1, f"no ambient fixtures placed for {r.name}"

    # Spot check: a bedroom should get several downlights, a small bathroom a few
    bedrooms = [r for r in project.rooms if r.type == RoomType.bedroom]
    if bedrooms:
        biggest_bedroom = max(bedrooms, key=lambda r: r.area_sqm)
        assert len(by_room[biggest_bedroom.id]) >= 4

    # Outdoor and staircase rooms should be empty
    outdoor_or_stair = [
        r for r in project.rooms
        if r.type in (RoomType.outdoor, RoomType.staircase)
    ]
    for r in outdoor_or_stair:
        assert by_room.get(r.id, []) == []
