import pytest

from lighting_engine.brief.models import LightingLayer, Zone
from lighting_engine.digest import compute_digest
from lighting_engine.digest.models import RoomDigest
from lighting_engine.lighting.task_layer import compute_task_layer
from lighting_engine.models.geometry import (
    FixtureSource,
    Furniture,
    Point,
    Project,
    Room,
    RoomType,
)
from lighting_engine.models.geometry import (
    LightingLayer as IRLayer,
)


def _dining_room_with_table() -> tuple[Room, RoomDigest]:
    room = Room(
        id="dining",
        name="DINING",
        type=RoomType.dining,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=5, y=0),
            Point(x=5, y=4),
            Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
    )
    room.furniture.append(
        Furniture(
            id="t1",
            type="dining_table",
            raw_label="dining table",
            position=Point(x=2.5, y=2.0),
        )
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    return room, digest


def test_task_layer_places_one_pendant_above_dining_table() -> None:
    room, digest = _dining_room_with_table()
    zone = Zone(
        layer=LightingLayer.task,
        purpose="task above dining table",
        cct_k=2700,
        cri_min=90,
        fixture_type="pendant",
        position_hint="above dining table",
    )
    fixtures = compute_task_layer(room, digest, zone)
    assert len(fixtures) == 1
    f = fixtures[0]
    assert f.position.x == pytest.approx(2.5)
    assert f.position.y == pytest.approx(2.0)
    assert f.source == FixtureSource.proposed
    assert f.layer == IRLayer.task
    assert f.type == "pendant"
    assert f.cct_k == 2700


def test_task_layer_downlight_uses_default_lumens() -> None:
    room, digest = _dining_room_with_table()
    zone = Zone(
        layer=LightingLayer.task,
        purpose="task over prep area",
        cct_k=4000,
        cri_min=90,
        fixture_type="downlight",
        position_hint="center",
    )
    fixtures = compute_task_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].lumens == pytest.approx(1500.0)
    assert fixtures[0].cct_k == 4000


def test_task_layer_unknown_fixture_type_falls_back_to_downlight() -> None:
    room, digest = _dining_room_with_table()
    zone = Zone(
        layer=LightingLayer.task,
        purpose="task light",
        cct_k=3000,
        cri_min=80,
        fixture_type="laser",  # invalid
        position_hint="center",
    )
    fixtures = compute_task_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].type == "downlight"
