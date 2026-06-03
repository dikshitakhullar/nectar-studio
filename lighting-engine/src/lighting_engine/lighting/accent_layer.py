"""Accent-layer placement: wash a wall, spot a feature, light an architectural detail.

For a "strip" TargetRegion (wall-aligned), place wall washers evenly along
the strip at ~0.8m spacing. For a "point" target, place a single spotlight.
"""

from lighting_engine.brief.models import Zone
from lighting_engine.digest import RoomDigest
from lighting_engine.lighting.zone_interpreter import interpret_position_hint
from lighting_engine.models.geometry import (
    Fixture,
    FixtureSource,
    LightingLayer,
    Point,
    Room,
)

# Target spacing between wall washers along a wall strip. Real installations
# pick exact spacing from the SKU's beam spread; 0.8m gives an even wash for
# 24°-beam track-style washers on a 2.7m ceiling.
_ACCENT_SPACING_M = 0.8

# Photometric defaults for accent fixtures (single-archetype v1).
_ACCENT_WATTAGE_W = 7.0
_ACCENT_LUMENS = 400.0
_ACCENT_BEAM_DEG = 24.0


def _strip_positions(
    room: Room, target_center: Point, wall_direction: str,
) -> list[Point]:
    """Evenly distribute fixtures along a wall strip at ~`_ACCENT_SPACING_M` apart.

    Uses centred spacing — first and last fixture sit `step/2` from the corner
    rather than `step`, which matches how a designer scales a wash off the
    wall ends (avoiding visible scallops at the corners).
    """
    polygon = room.polygon
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    if wall_direction in ("N", "S"):
        wall_min, wall_max = min(xs), max(xs)
        wall_len = wall_max - wall_min
        count = max(1, int(wall_len / _ACCENT_SPACING_M))
        step = wall_len / count
        return [
            Point(x=wall_min + step * (i + 0.5), y=target_center.y)
            for i in range(count)
        ]
    # E / W
    wall_min, wall_max = min(ys), max(ys)
    wall_len = wall_max - wall_min
    count = max(1, int(wall_len / _ACCENT_SPACING_M))
    step = wall_len / count
    return [
        Point(x=target_center.x, y=wall_min + step * (i + 0.5))
        for i in range(count)
    ]


def compute_accent_layer(
    room: Room,
    digest: RoomDigest,
    zone: Zone,
) -> list[Fixture]:
    """Place accent fixtures: wall washers along a strip, or one spotlight at a point."""
    target = interpret_position_hint(zone.position_hint, room, digest)
    if target.region_type == "strip" and target.wall_direction is not None:
        positions = _strip_positions(room, target.center, target.wall_direction)
        fixture_type = zone.fixture_type or "wall_washer"
    else:
        positions = [target.center]
        # A point target on the accent layer always reads as a spotlight
        # regardless of what the brief asked for — accent + point = spot.
        fixture_type = "spotlight"

    fallback_note = (
        f" (fallback: {target.fallback_reason})" if target.fallback_reason else ""
    )
    reasoning = (
        f"Accent layer: {zone.purpose}. {fixture_type} placed at "
        f"{zone.position_hint!r}{fallback_note}"
    )

    return [
        Fixture(
            id=f"{room.id}-acc-{i:03d}",
            type=fixture_type,
            position=pos,
            mount_height_m=None,
            source=FixtureSource.proposed,
            layer=LightingLayer.accent,
            reasoning=reasoning,
            wattage_w=_ACCENT_WATTAGE_W,
            lumens=_ACCENT_LUMENS,
            cct_k=zone.cct_k,
            cri=zone.cri_min,
            beam_angle_deg=_ACCENT_BEAM_DEG,
        )
        for i, pos in enumerate(positions)
    ]
