"""Convert a brief Zone's semantic position_hint into a geometric target region.

The LLM emits zones like "above dining table" or "wall N near window" — never
coordinates. This module translates those hints into a TargetRegion that the
per-layer placement code consumes.

Hints we recognize (case-insensitive substring match):
  - "center" / "center of ceiling" → centroid point, 0.5m radius
  - "above <furniture>" → centroid of the named furniture's bounding box
  - "wall N" / "wall S" / "wall E" / "wall W" → 0.6m strip along that wall
  - "perimeter" / "perimeter cove" → polygon outline, 0.3m wide
  - anything else → centroid fallback, fallback_reason set
"""

from dataclasses import dataclass

from lighting_engine.digest import RoomDigest
from lighting_engine.models.geometry import Point, Room

# Half-depth of a wall strip target (0.6m strip → 0.3m offset from wall plane).
_WALL_STRIP_DEPTH_M = 0.6
_WALL_STRIP_HALF_DEPTH_M = _WALL_STRIP_DEPTH_M / 2.0

# Perimeter cove strip width.
_PERIMETER_DEPTH_M = 0.3

# Default radius for point-type targets (centroid / above-furniture).
_POINT_RADIUS_M = 0.5


@dataclass(frozen=True)
class TargetRegion:
    """Geometric region a zone's fixtures should be placed within.

    region_type:
      - "point"     : single placement point at `center`, with `radius_m` slack.
      - "strip"     : along a wall — `center` is the strip midpoint;
                      `wall_direction` is N/S/E/W; `depth_m` is the strip depth.
      - "perimeter" : along the full polygon outline; `depth_m` is strip width.
    """

    region_type: str
    center: Point
    radius_m: float = _POINT_RADIUS_M
    depth_m: float = 0.0
    wall_direction: str | None = None
    fallback_reason: str | None = None


def _polygon_centroid(polygon: list[Point]) -> Point:
    """Arithmetic centroid of the polygon vertices.

    Adequate for the rectilinear residential rooms v1 supports; not the area
    centroid, but the difference is sub-decimetre for the room shapes we see.
    """
    n = len(polygon)
    cx = sum(p.x for p in polygon) / n
    cy = sum(p.y for p in polygon) / n
    return Point(x=cx, y=cy)


def _wall_strip(room: Room, direction: str) -> Point:
    """Return the strip-center point for the polygon edge in `direction`.

    The strip sits parallel to the wall, half-depth inside the room so the
    fixtures don't overlap the wall plane.
    """
    polygon = room.polygon
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    if direction == "N":
        cx = (min(xs) + max(xs)) / 2.0
        return Point(x=cx, y=max(ys) - _WALL_STRIP_HALF_DEPTH_M)
    if direction == "S":
        cx = (min(xs) + max(xs)) / 2.0
        return Point(x=cx, y=min(ys) + _WALL_STRIP_HALF_DEPTH_M)
    if direction == "E":
        cy = (min(ys) + max(ys)) / 2.0
        return Point(x=max(xs) - _WALL_STRIP_HALF_DEPTH_M, y=cy)
    # W
    cy = (min(ys) + max(ys)) / 2.0
    return Point(x=min(xs) + _WALL_STRIP_HALF_DEPTH_M, y=cy)


def _named_furniture_center(room: Room, name_substring: str) -> Point | None:
    """Return the position of the first furniture whose label/type contains the substring."""
    needle = name_substring.lower().strip()
    if not needle:
        return None
    for f in room.furniture:
        label = (f.raw_label or f.type or "").lower()
        if needle in label:
            return f.position
    return None


def interpret_position_hint(
    hint: str,
    room: Room,
    digest: RoomDigest,
) -> TargetRegion:
    """Convert a position_hint string into a TargetRegion on the room polygon.

    The interpretation order matters: "perimeter" takes precedence over the
    word "center"; "above <x>" is checked before wall hints so an "above
    dining table on wall N" hint resolves to the furniture, not the wall.
    Unknown hints fall back to the room centroid with `fallback_reason` set
    so callers (and the report) can surface the degradation.
    """
    h = hint.lower().strip()

    if "perimeter" in h:
        return TargetRegion(
            region_type="perimeter",
            center=_polygon_centroid(room.polygon),
            depth_m=_PERIMETER_DEPTH_M,
        )

    if h.startswith("above "):
        needle = h[len("above "):].strip()
        pos = _named_furniture_center(room, needle)
        if pos is not None:
            return TargetRegion(
                region_type="point",
                center=pos,
                radius_m=_POINT_RADIUS_M,
            )
        # fall through to wall/center/fallback handling

    for direction in ("N", "S", "E", "W"):
        if f"wall {direction.lower()}" in h or f"wall {direction}" in h:
            center = _wall_strip(room, direction)
            return TargetRegion(
                region_type="strip",
                center=center,
                depth_m=_WALL_STRIP_DEPTH_M,
                wall_direction=direction,
            )

    if "center" in h:
        return TargetRegion(
            region_type="point",
            center=_polygon_centroid(room.polygon),
            radius_m=_POINT_RADIUS_M,
        )

    return TargetRegion(
        region_type="point",
        center=_polygon_centroid(room.polygon),
        radius_m=_POINT_RADIUS_M,
        fallback_reason=f"unrecognised hint: {hint!r}",
    )
