"""Accent-layer placement: wash a wall, spot a feature, light an architectural detail.

For a "strip" TargetRegion (wall-aligned), place wall washers evenly along
the strip at ~1.5m spacing, capped at 3 per wall. Walls with windows or
doors skip wall-washer placement entirely (washes belong on solid feature
walls, not over openings). For a "point" target, place a single spotlight.

These are v1 residential heuristics. A real designer picks spacing from the
fixture's beam spread + the specific feature being lit; v2 brings that in.
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

# Spacing between wall washers along a wall strip. 1.5m matches residential
# practice — closer than that on a typical 2.7m ceiling looks commercial /
# gallery-style. v2 will pick spacing from the fixture's beam spread.
_ACCENT_SPACING_M = 1.5

# Hard cap on wall washers per wall. Residential walls almost never need
# more than 3 grazers; beyond that it reads as continuous wash, which is a
# different design intent (cove, not accent).
_MAX_GRAZERS_PER_WALL = 3

# Photometric defaults for accent fixtures (single-archetype v1).
_ACCENT_WATTAGE_W = 7.0
_ACCENT_LUMENS = 400.0
_ACCENT_BEAM_DEG = 24.0


def _wall_has_opening(room: Room, wall_direction: str) -> bool:
    """True if any door or window in this room sits on the wall facing
    ``wall_direction``.

    The check picks each opening's wall edge midpoint and tests whether
    the direction from the room centroid to that midpoint matches the
    given cardinal direction (N/S/E/W). Approximation that works for
    rectangular and modestly-non-rectangular rooms.
    """
    if not room.polygon:
        return False
    centroid_x = sum(p.x for p in room.polygon) / len(room.polygon)
    centroid_y = sum(p.y for p in room.polygon) / len(room.polygon)
    n = len(room.polygon)
    openings: list = list(room.doors) + list(room.windows)
    for opening in openings:
        wi = getattr(opening, "wall_index", None)
        if wi is None or wi >= n:
            continue
        a = room.polygon[wi]
        b = room.polygon[(wi + 1) % n]
        dx = (a.x + b.x) / 2 - centroid_x
        dy = (a.y + b.y) / 2 - centroid_y
        if wall_direction == "N" and dy > abs(dx):
            return True
        if wall_direction == "S" and -dy > abs(dx):
            return True
        if wall_direction == "E" and dx > abs(dy):
            return True
        if wall_direction == "W" and -dx > abs(dy):
            return True
    return False


def _strip_positions(
    room: Room, target_center: Point, wall_direction: str,
) -> list[Point]:
    """Distribute up to `_MAX_GRAZERS_PER_WALL` fixtures along a wall strip
    at ~`_ACCENT_SPACING_M` apart.

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
        count = min(_MAX_GRAZERS_PER_WALL,
                    max(1, int(wall_len / _ACCENT_SPACING_M)))
        step = wall_len / count
        return [
            Point(x=wall_min + step * (i + 0.5), y=target_center.y)
            for i in range(count)
        ]
    # E / W
    wall_min, wall_max = min(ys), max(ys)
    wall_len = wall_max - wall_min
    count = min(_MAX_GRAZERS_PER_WALL,
                max(1, int(wall_len / _ACCENT_SPACING_M)))
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
    """Place accent fixtures: wall washers along a strip, or one spotlight at a point.

    Walls with openings (doors / windows) skip the wall-wash treatment entirely
    and fall back to a single spotlight at the wall midpoint — wall grazers
    behind a window curtain rod or over a doorway are a v1 footgun.
    """
    target = interpret_position_hint(zone.position_hint, room, digest)
    if target.region_type == "strip" and target.wall_direction is not None:
        if _wall_has_opening(room, target.wall_direction):
            # Don't wash a wall that has a window or door. Fall back to a
            # single spot at the wall midpoint — the designer can move it
            # to a real feature in the studio.
            positions = [target.center]
            fixture_type = "spotlight"
        else:
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
