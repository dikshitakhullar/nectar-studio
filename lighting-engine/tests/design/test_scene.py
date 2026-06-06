import pytest
from pydantic import ValidationError

from lighting_engine.design.scene import (
    CeilingZone,
    FocalPoint,
    RoomScene,
    WallPurpose,
)
from lighting_engine.models.geometry import Point


def test_wall_purpose_round_trip():
    w = WallPurpose(
        wall_index=2, purpose="headboard",
        features=["king-size bed against this wall"], confidence=0.9,
    )
    assert w.wall_index == 2
    assert w.purpose == "headboard"
    # Frozen — direct mutation should fail
    with pytest.raises(ValidationError):
        w.wall_index = 5  # type: ignore[misc]
    # And construction with an out-of-range wall_index is rejected
    with pytest.raises(ValidationError):
        WallPurpose(wall_index=-1, purpose="headboard", confidence=0.9)


def test_wall_purpose_rejects_unknown_purpose():
    with pytest.raises(ValidationError):
        WallPurpose(wall_index=0, purpose="bogus", confidence=0.5)


def test_ceiling_zone_accepts_all_types():
    for t in ("cove", "flat", "level_change", "fluted", "tray"):
        cz = CeilingZone(type=t, description=f"the {t} zone", confidence=0.8)
        assert cz.type == t


def test_focal_point_with_real_position():
    fp = FocalPoint(
        type="bed", position=Point(x=2.5, y=1.2),
        purpose_hint="head end faces south, against wall 2",
    )
    assert fp.type == "bed"
    assert fp.position.x == 2.5


def test_room_scene_defaults_to_empty():
    scene = RoomScene(confidence=0.9)
    assert scene.walls == []
    assert scene.ceiling == []
    assert scene.focal_points == []
    assert scene.notes == ""


def test_room_scene_full_round_trip():
    scene = RoomScene(
        walls=[WallPurpose(wall_index=0, purpose="headboard", confidence=0.9)],
        ceiling=[CeilingZone(type="cove", description="perimeter cove", confidence=0.85)],
        focal_points=[FocalPoint(
            type="bed", position=Point(x=2.0, y=1.5),
            purpose_hint="centered on wall 0",
        )],
        notes="Master bedroom with cove ceiling and bed against north wall.",
        confidence=0.88,
    )
    serialized = scene.model_dump(mode="json")
    rebuilt = RoomScene.model_validate(serialized)
    assert rebuilt == scene
