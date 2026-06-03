"""Filter window segments to those that sit on an interior room's wall.

The window-layer (and GLASS) in a DWG often contains linework that is not a
real window: balcony parapets, terrace planters, glazed-roof boundary detail,
courtyard parapets. Naively trusting every LINE/LWPOLYLINE on those layers
generates phantom windows on outdoor surfaces — the most common complaint
from designers reviewing parsed plans.

A window only makes sense as part of a *room's wall*. This module enforces
that constraint: a window segment is kept only if it sits adjacent to an
interior room polygon edge, parallel to it, and overlapping it by at least
half its own length. Anything else is dropped as terrace/balcony/courtyard
boundary detail.

Coordinates throughout this module are in the local-meter frame (matching
the Room polygon convention and the `Segment` alias from `parser/snap.py`).
"""

import math

from lighting_engine.models.geometry import Room, RoomType

# We reuse the geometry helpers from snap.py rather than reimplementing them.
# They're spelled with a leading underscore for module-internal style but are
# the canonical implementations of these primitives in this package — this
# filter is part of the same parser subsystem, so the cross-module reuse is
# intentional. Pyright's reportPrivateUsage is silenced for the underscored
# names; `Segment` is a public alias.
from lighting_engine.parser.snap import (
    Segment,
    _angle_between_deg,  # pyright: ignore[reportPrivateUsage]
    _overlap_fraction,  # pyright: ignore[reportPrivateUsage]
    _perp_distance_point_to_line,  # pyright: ignore[reportPrivateUsage]
    _WallLine,  # pyright: ignore[reportPrivateUsage]
)

# --- Tunable thresholds ---------------------------------------------------
# Perpendicular distance from window midpoint to room edge infinite line, in
# meters. 0.4m allows the window to sit on the inside or outside face of a
# wall (Indian residential walls ~0.23m thick) without losing the match.
_MAX_PERP_DIST_M = 0.4
# Angle between window direction and room-edge direction; matches the snap
# module's 15° tolerance for off-square rooms.
_MAX_PARALLEL_DEG = 15.0
# Fraction of the WINDOW length that must overlap the room edge (projected
# onto the room edge's direction). 0.5 = the edge must cover at least half
# of the window — a window can be a fraction of a long wall, but cannot
# stick out past it.
_MIN_OVERLAP_FRAC = 0.5

# Room names that should be treated as outdoors regardless of their RoomType.
# The Delhi golden file marks TERRACE as `outdoor`, but BALCONY rooms are
# sometimes typed as `unknown`. Catching them by name keeps the filter
# correct without changing the layer classifier or Room model.
_OUTDOOR_NAME_HINTS: tuple[str, ...] = ("terrace", "balcony")


def _is_interior_room(room: Room) -> bool:
    """Return True if this room can plausibly own a window.

    Excludes:
      - outdoor and staircase room types (windows don't belong to either)
      - rooms whose name contains 'TERRACE' or 'BALCONY' (case-insensitive),
        which are mislabeled outdoors in the current Delhi golden file
    """
    if room.type in (RoomType.outdoor, RoomType.staircase):
        return False
    lower = room.name.lower()
    return not any(hint in lower for hint in _OUTDOOR_NAME_HINTS)


def _build_wall_line(
    p1: tuple[float, float], p2: tuple[float, float]
) -> _WallLine | None:
    """Build a `_WallLine` from two endpoints. Returns None for degenerate input."""
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if length <= 0.0:
        return None
    return _WallLine(
        p1=p1,
        p2=p2,
        dx=(p2[0] - p1[0]) / length,
        dy=(p2[1] - p1[1]) / length,
        length=length,
    )


def _interior_room_edges(rooms: list[Room]) -> list[_WallLine]:
    """Collect every polygon edge from every interior room as a `_WallLine`."""
    out: list[_WallLine] = []
    for room in rooms:
        if not _is_interior_room(room):
            continue
        polygon = room.polygon
        n = len(polygon)
        if n < 3:
            continue
        for i in range(n):
            a = polygon[i]
            b = polygon[(i + 1) % n]
            line = _build_wall_line((a.x, a.y), (b.x, b.y))
            if line is not None:
                out.append(line)
    return out


def _segment_matches_any_edge(
    segment: Segment,
    edges: list[_WallLine],
    *,
    max_perp: float,
    max_angle_deg: float,
    min_overlap: float,
) -> bool:
    """Return True if `segment` is plausibly on at least one room edge."""
    (ax, ay), (bx, by) = segment
    seg_dx = bx - ax
    seg_dy = by - ay
    seg_len = math.hypot(seg_dx, seg_dy)
    if seg_len <= 0.0:
        return False
    s_ux = seg_dx / seg_len
    s_uy = seg_dy / seg_len
    mx = (ax + bx) / 2
    my = (ay + by) / 2

    for edge in edges:
        if _angle_between_deg(s_ux, s_uy, edge.dx, edge.dy) > max_angle_deg:
            continue
        if _perp_distance_point_to_line(mx, my, edge) > max_perp:
            continue
        if _overlap_fraction(ax, ay, bx, by, edge) < min_overlap:
            continue
        return True
    return False


def filter_valid_windows(
    window_segments: list[Segment],
    interior_rooms: list[Room],
    *,
    max_perp_dist_m: float = _MAX_PERP_DIST_M,
    max_parallel_deg: float = _MAX_PARALLEL_DEG,
    min_overlap_frac: float = _MIN_OVERLAP_FRAC,
) -> tuple[list[Segment], list[Segment]]:
    """Split window segments into (kept, dropped).

    A segment is KEPT if it sits adjacent to at least one interior room
    polygon edge:
      1. perpendicular distance from segment midpoint to the edge's infinite
         line is within `max_perp_dist_m`,
      2. the segment is parallel within `max_parallel_deg` of that edge,
      3. at least `min_overlap_frac` of the segment's length is covered by
         the edge (projection-overlap test).

    Interior rooms are filtered via `_is_interior_room` — callers may pass
    a pre-filtered list, or the full room set (this function will re-filter).

    Pure function. Order within each returned list mirrors `window_segments`.
    """
    interior = [r for r in interior_rooms if _is_interior_room(r)]
    edges = _interior_room_edges(interior)

    kept: list[Segment] = []
    dropped: list[Segment] = []
    if not edges:
        # No interior rooms → no segment can be on an interior wall.
        return kept, list(window_segments)

    for seg in window_segments:
        if _segment_matches_any_edge(
            seg, edges,
            max_perp=max_perp_dist_m,
            max_angle_deg=max_parallel_deg,
            min_overlap=min_overlap_frac,
        ):
            kept.append(seg)
        else:
            dropped.append(seg)
    return kept, dropped
