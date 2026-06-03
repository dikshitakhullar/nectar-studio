import pytest

from lighting_engine.brief.models import LightingLayer, Zone
from lighting_engine.digest import compute_digest
from lighting_engine.digest.models import RoomDigest
from lighting_engine.lighting.accent_layer import compute_accent_layer
from lighting_engine.models.geometry import (
    FixtureSource,
    Point,
    Project,
    Room,
    RoomType,
)
from lighting_engine.models.geometry import (
    LightingLayer as IRLayer,
)


def _living_room() -> tuple[Room, RoomDigest]:
    room = Room(
        id="living",
        name="LIVING",
        type=RoomType.living,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=4, y=0),
            Point(x=4, y=4),
            Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    return room, digest


def test_accent_layer_places_washers_along_wall_n_at_080m_spacing() -> None:
    room, digest = _living_room()
    zone = Zone(
        layer=LightingLayer.accent,
        purpose="wash north wall art",
        cct_k=3000,
        cri_min=90,
        fixture_type="wall_washer",
        position_hint="wall N",
    )
    fixtures = compute_accent_layer(room, digest, zone)
    # 4m wall, 0.8m spacing → 5 positions (0.4, 1.2, 2.0, 2.8, 3.6)
    assert len(fixtures) == 5
    xs = sorted(f.position.x for f in fixtures)
    assert xs[0] == pytest.approx(0.4)
    assert xs[-1] == pytest.approx(3.6)
    # All sit at the wall strip y position
    for f in fixtures:
        assert f.position.y == pytest.approx(3.7)  # 4.0 - 0.3
        assert f.source == FixtureSource.proposed
        assert f.layer == IRLayer.accent


def test_accent_layer_point_target_places_single_spotlight() -> None:
    room, digest = _living_room()
    zone = Zone(
        layer=LightingLayer.accent,
        purpose="accent on feature niche",
        cct_k=3000,
        cri_min=90,
        fixture_type="spotlight",
        position_hint="center",
    )
    fixtures = compute_accent_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].type == "spotlight"
    assert fixtures[0].position.x == pytest.approx(2.0)
    assert fixtures[0].position.y == pytest.approx(2.0)
