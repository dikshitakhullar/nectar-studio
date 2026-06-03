import pytest

from lighting_engine.brief.models import LightingLayer, Zone
from lighting_engine.digest import compute_digest
from lighting_engine.digest.models import RoomDigest
from lighting_engine.lighting.decorative_layer import compute_decorative_layer
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


def _drawing_room() -> tuple[Room, RoomDigest]:
    room = Room(
        id="dr",
        name="DRAWING ROOM",
        type=RoomType.living,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=6, y=0),
            Point(x=6, y=5),
            Point(x=0, y=5),
        ],
        ceiling_height_m=3.0,
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    return room, digest


def test_decorative_places_one_chandelier_at_center() -> None:
    room, digest = _drawing_room()
    zone = Zone(
        layer=LightingLayer.decorative,
        purpose="statement chandelier",
        cct_k=2700,
        cri_min=90,
        fixture_type="chandelier",
        position_hint="center",
    )
    fixtures = compute_decorative_layer(room, digest, zone)
    assert len(fixtures) == 1
    f = fixtures[0]
    assert f.position.x == pytest.approx(3.0)
    assert f.position.y == pytest.approx(2.5)
    assert f.type == "chandelier"
    assert f.source == FixtureSource.proposed
    assert f.layer == IRLayer.decorative
    assert f.lumens == pytest.approx(3000.0)
    assert f.wattage_w == pytest.approx(45.0)


def test_decorative_pendant_at_above_table() -> None:
    room, _ = _drawing_room()
    room.furniture.append(
        Furniture(
            id="t",
            type="coffee_table",
            raw_label="coffee table",
            position=Point(x=3.0, y=2.5),
        )
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    zone = Zone(
        layer=LightingLayer.decorative,
        purpose="feature pendant cluster",
        cct_k=2700,
        cri_min=90,
        fixture_type="pendant",
        position_hint="above coffee table",
    )
    fixtures = compute_decorative_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].position.x == pytest.approx(3.0)
    assert fixtures[0].position.y == pytest.approx(2.5)
