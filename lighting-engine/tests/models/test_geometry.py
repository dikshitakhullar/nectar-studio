import pytest
from pydantic import ValidationError

from lighting_engine.models.geometry import (
    CeilingFeature,
    Door,
    DoorSwing,
    Fixture,
    Furniture,
    Point,
    Project,
    Room,
    RoomType,
    Window,
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


def test_window_along_wall_rejects_out_of_range():
    # In range works
    Window(
        id="w1",
        wall_index=0,
        along_wall=0.5,
        width_m=1.2,
        height_m=1.5,
        sill_height_m=0.9,
        is_glazed_door=False,
    )
    # Out of range rejected
    with pytest.raises(ValidationError):
        Window(
            id="w2",
            wall_index=0,
            along_wall=1.5,
            width_m=1.2,
            height_m=1.5,
            sill_height_m=0.9,
            is_glazed_door=False,
        )
    with pytest.raises(ValidationError):
        Window(
            id="w3",
            wall_index=0,
            along_wall=-0.1,
            width_m=1.2,
            height_m=1.5,
            sill_height_m=0.9,
            is_glazed_door=False,
        )


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


def test_door_defaults():
    d = Door(id="d1", wall_index=0, along_wall=0.5, width_m=0.9)
    assert d.swing == DoorSwing.unknown
    assert d.height_m == pytest.approx(2.1)


def test_door_swing_serializes_to_in_not_in_underscore():
    d = Door(id="d1", wall_index=0, along_wall=0.5, width_m=0.9, swing=DoorSwing.in_)
    assert d.model_dump()["swing"] == "in"


def test_furniture_footprint_defaults_empty_and_label_optional():
    f = Furniture(id="f1", position=Point(x=0, y=0))
    assert f.footprint == []
    assert f.raw_label is None
    assert f.type == "unknown"


def test_fixture_mount_height_defaults_to_none_for_ceiling_mounted():
    fx = Fixture(id="fx1", position=Point(x=1, y=2))
    assert fx.mount_height_m is None


def test_ceiling_feature_rejects_polygon_with_fewer_than_3_points():
    with pytest.raises(ValidationError):
        CeilingFeature(
            id="cf1",
            kind="beam",
            polygon=[Point(x=0, y=0), Point(x=1, y=0)],
        )


def test_ceiling_feature_constructs_with_valid_polygon():
    cf = CeilingFeature(
        id="cf2",
        kind="cove",
        polygon=[Point(x=0, y=0), Point(x=4, y=0), Point(x=4, y=1)],
        depth_m=0.15,
    )
    assert cf.depth_m == pytest.approx(0.15)
