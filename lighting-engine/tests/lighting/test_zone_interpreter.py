import pytest

from lighting_engine.digest import compute_digest
from lighting_engine.lighting.zone_interpreter import (
    TargetRegion,
    interpret_position_hint,
)
from lighting_engine.models.geometry import (
    Furniture,
    Point,
    Project,
    Room,
    RoomType,
)


def _rect_room(name: str, type_: RoomType, side: float = 5.0) -> Room:
    s = side / 2
    return Room(
        id=name.lower(),
        name=name,
        type=type_,
        floor_level=0,
        polygon=[
            Point(x=-s, y=-s),
            Point(x=s, y=-s),
            Point(x=s, y=s),
            Point(x=-s, y=s),
        ],
        ceiling_height_m=2.7,
    )


def test_center_hint_returns_centroid_with_small_radius() -> None:
    room = _rect_room("Living", RoomType.living)
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("center", room, digest)
    assert isinstance(target, TargetRegion)
    assert target.region_type == "point"
    assert target.center.x == pytest.approx(0.0)
    assert target.center.y == pytest.approx(0.0)
    assert target.radius_m == pytest.approx(0.5)


def test_wall_n_hint_returns_north_strip() -> None:
    room = _rect_room("Dining", RoomType.dining)
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("wall N", room, digest)
    assert target.region_type == "strip"
    # North wall is the polygon edge at y = 2.5 for our 5x5 room
    assert target.center.y == pytest.approx(2.5 - 0.3)
    assert target.depth_m == pytest.approx(0.6)


def test_above_furniture_hint_returns_furniture_bbox() -> None:
    room = _rect_room("Dining", RoomType.dining)
    room.furniture.append(
        Furniture(
            id="f1",
            type="dining_table",
            raw_label="dining table",
            position=Point(x=0.5, y=-0.2),
        )
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("above dining table", room, digest)
    assert target.region_type == "point"
    assert target.center.x == pytest.approx(0.5)
    assert target.center.y == pytest.approx(-0.2)


def test_perimeter_hint_returns_perimeter_strip() -> None:
    room = _rect_room("Living", RoomType.living)
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("perimeter", room, digest)
    assert target.region_type == "perimeter"
    assert target.depth_m == pytest.approx(0.3)


def test_unknown_hint_falls_back_to_centroid() -> None:
    room = _rect_room("Living", RoomType.living)
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("over the chaise lounge", room, digest)
    assert target.region_type == "point"
    assert target.center.x == pytest.approx(0.0)
    assert target.fallback_reason is not None
