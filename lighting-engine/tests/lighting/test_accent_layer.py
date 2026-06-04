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


def test_accent_layer_places_residential_count_of_washers() -> None:
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
    # 4m wall, 1.5m spacing → int(4 / 1.5) = 2 grazers (residential heuristic).
    # Cap is 3; on a 4m wall we naturally land at 2 — gallery-style 5-grazer
    # rows were the old 0.8m spacing and looked commercial in residential.
    assert len(fixtures) == 2
    xs = sorted(f.position.x for f in fixtures)
    assert xs[0] == pytest.approx(1.0)   # 4 / 2 = step 2; centered → 0 + 1
    assert xs[-1] == pytest.approx(3.0)  # 2 + 1
    # All sit at the wall strip y position
    for f in fixtures:
        assert f.position.y == pytest.approx(3.7)  # 4.0 - 0.3
        assert f.source == FixtureSource.proposed
        assert f.layer == IRLayer.accent


def test_accent_layer_caps_grazers_at_three_per_wall() -> None:
    """A 10m wall would yield 6 grazers at 1.5m spacing — cap to 3."""
    room = Room(
        id="long_room",
        name="LONG",
        type=RoomType.living,
        floor_level=0,
        polygon=[
            Point(x=0, y=0), Point(x=10, y=0),
            Point(x=10, y=4), Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    zone = Zone(
        layer=LightingLayer.accent, purpose="wash north wall",
        cct_k=3000, cri_min=90,
        fixture_type="wall_washer", position_hint="wall N",
    )
    fixtures = compute_accent_layer(room, digest, zone)
    assert len(fixtures) == 3


def test_accent_layer_skips_wash_on_windowed_wall() -> None:
    """Wall with a window gets a single spotlight, not a row of grazers."""
    from lighting_engine.models.geometry import Window
    room = Room(
        id="window_room", name="WIN", type=RoomType.living, floor_level=0,
        polygon=[
            Point(x=0, y=0), Point(x=4, y=0),
            Point(x=4, y=4), Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
        windows=[Window(
            id="w1", position=Point(x=2, y=4),
            wall_index=2,  # the N-facing edge (y=4 → top)
            width_m=1.2, height_m=1.2, sill_height_m=0.9,
        )],
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    zone = Zone(
        layer=LightingLayer.accent, purpose="wash north wall",
        cct_k=3000, cri_min=90,
        fixture_type="wall_washer", position_hint="wall N",
    )
    fixtures = compute_accent_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].type == "spotlight"


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
