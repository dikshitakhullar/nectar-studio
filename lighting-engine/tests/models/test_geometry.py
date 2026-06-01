import pytest
from pydantic import ValidationError

from lighting_engine.models.geometry import (
    Point,
    RoomType,
    Window,
    Door,
    Furniture,
    Fixture,
    CeilingFeature,
    Room,
    Project,
)


def test_point_is_two_floats():
    p = Point(x=1.5, y=-2.0)
    assert p.x == 1.5
    assert p.y == -2.0


def test_room_computes_area_from_polygon():
    # 4m x 3m rectangle → 12 sqm
    poly = [Point(x=0, y=0), Point(x=4, y=0), Point(x=4, y=3), Point(x=0, y=3)]
    room = Room(id="r1", name="Living", type=RoomType.living, polygon=poly, ceiling_height_m=2.7)
    assert room.area_sqm == pytest.approx(12.0)


def test_room_rejects_polygon_with_fewer_than_3_points():
    with pytest.raises(ValidationError):
        Room(
            id="r1",
            name="x",
            type=RoomType.living,
            polygon=[Point(x=0, y=0), Point(x=1, y=0)],
            ceiling_height_m=2.7,
        )


def test_window_position_along_wall_is_clamped():
    # along_wall is a 0..1 fraction
    w = Window(id="w1", wall_index=0, along_wall=0.5, width_m=1.2, height_m=1.5, sill_height_m=0.9, is_glazed_door=False)
    assert 0 <= w.along_wall <= 1


def test_project_serializes_to_json_round_trip():
    poly = [Point(x=0, y=0), Point(x=4, y=0), Point(x=4, y=3), Point(x=0, y=3)]
    room = Room(id="r1", name="Living", type=RoomType.living, polygon=poly, ceiling_height_m=2.7)
    proj = Project(
        id="p1",
        name="Mohak Residence",
        location="delhi",
        floor_level=0,
        north_orientation_deg=0.0,
        rooms=[room],
    )
    data = proj.model_dump_json()
    restored = Project.model_validate_json(data)
    assert restored.rooms[0].area_sqm == pytest.approx(12.0)


def test_room_type_enum_includes_all_residential_spaces():
    expected = {"living", "dining", "bedroom", "kitchen", "bathroom",
                "study", "hallway", "staircase", "foyer", "outdoor", "unknown"}
    assert {rt.value for rt in RoomType} == expected
