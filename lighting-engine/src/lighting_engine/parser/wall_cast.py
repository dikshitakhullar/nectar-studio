"""Translate room polygons to touch bounding walls (large-scale ray-cast).

After label-based placement, some room polygons sit metres away from their
actual bounding walls — the label is just a positional hint, not a guarantee.
The wall-snap module fixes small (<0.8m) edge misalignments by re-projecting
edges, but cannot help when the polygon is metres from any qualifying wall.

This module casts four cardinal rays from each room's polygon bbox and
translates the polygon so its edges touch the nearest qualifying perpendicular
walls in each direction. **Translation preserves size** — only position
changes. Must run BEFORE the wall-snap step so snap can do its fine-grained
refinement on a polygon already in the right wall-bounded region.

Algorithm per room:
  1. Compute polygon bbox: (minx, miny, maxx, maxy).
  2. For each cardinal direction, find the closest qualifying wall OUTSIDE
     the polygon in that direction. Wall must be predominantly perpendicular
     to the cast direction (within 20°) and must span ≥50% of the polygon's
     perpendicular extent (so the wall actually bounds the polygon edge).
  3. Resolve a per-axis translation:
       - Both walls found AND polygon width matches wall-bounded gap within
         ±15%: center the polygon between the walls.
       - Both walls found but polygon smaller: snap to the closer wall.
       - One wall found: translate polygon edge to touch it.
       - Neither found: no translation for that axis.
  4. Apply translation only if a component exceeds `min_significant_gap_m`
     (small misalignments left for the wall-snap step). Reject if any axis
     would translate by more than `max_translation_m` (likely false-positive
     across-building cast).

Coordinates are in the local-meter frame (matching Room.polygon convention).
The caller is responsible for converting DXF-unit walls into local meters.
"""

import math
from dataclasses import dataclass

from shapely.geometry import Polygon as ShapelyPolygon

from lighting_engine.models.geometry import Point, Room

Segment = tuple[tuple[float, float], tuple[float, float]]

# --- Tunable thresholds ----------------------------------------------------
# Max distance from polygon edge to qualifying wall. Beyond this, we assume the
# wall is across an unrelated room — don't trust the cast.
_MAX_CAST_DIST_M = 6.0
# Wall direction must be within this many degrees of perpendicular to the ray
# (i.e. for an X-axis ray we want walls that are predominantly vertical).
_PERPENDICULAR_TOL_DEG = 20.0
# Tiny segments (drafting noise) shouldn't act as bounding walls. 0.3m
# admits door-jamb fragments and wall stubs broken by openings.
_MIN_WALL_SPAN_M = 0.3
# Wall fragments at the same axis position are aggregated (their Y-overlaps
# with the polygon are unioned). The COLLECTIVE overlap must reach this
# fraction of the polygon's perpendicular extent. 0.25 admits walls broken
# by doors and windows — typical interior wall is ~30-50% wall, 50-70%
# opening when room has a door + window.
_MIN_PERPENDICULAR_OVERLAP_FRAC = 0.25
# Tolerance for grouping wall fragments along the cast axis (X for vertical
# walls, Y for horizontal). Wall thickness is ~0.2m so fragments may sit at
# slightly different recorded centerlines.
_AXIS_GROUP_TOL_M = 0.2
# Don't translate at all unless the gap exceeds this — small gaps are the
# snap module's job.
_MIN_SIGNIFICANT_GAP_M = 0.6
# Hard cap on translation. Beyond this we probably found the wrong wall
# (e.g. a wall behind another room).
_MAX_TRANSLATION_M = 6.0


@dataclass(frozen=True)
class _WallLine:
    p1: tuple[float, float]
    p2: tuple[float, float]
    length: float
    is_vertical: bool
    is_horizontal: bool


def _build_walls(segments: list[Segment]) -> list[_WallLine]:
    out: list[_WallLine] = []
    for (x1, y1), (x2, y2) in segments:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < _MIN_WALL_SPAN_M:
            continue
        dx = (x2 - x1) / length
        dy = (y2 - y1) / length
        angle_from_horizontal = math.degrees(math.atan2(abs(dy), abs(dx)))
        is_vertical = abs(angle_from_horizontal - 90.0) <= _PERPENDICULAR_TOL_DEG
        is_horizontal = angle_from_horizontal <= _PERPENDICULAR_TOL_DEG
        if not (is_vertical or is_horizontal):
            continue
        out.append(_WallLine(
            p1=(x1, y1), p2=(x2, y2),
            length=length,
            is_vertical=is_vertical, is_horizontal=is_horizontal,
        ))
    return out


def _polygon_bbox(polygon: list[Point]) -> tuple[float, float, float, float]:
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _collective_overlap_at_x(
    target_x: float,
    walls: list[_WallLine],
    polygon_miny: float, polygon_maxy: float,
    axis_tol: float = _AXIS_GROUP_TOL_M,
) -> float:
    """Sum the union of Y-overlaps for all vertical walls within `axis_tol` of
    `target_x` against [polygon_miny, polygon_maxy].

    A wall broken by doors/windows shows up as multiple fragments at the same
    X — this aggregates them so the collective wall is what gets measured.
    """
    intervals: list[tuple[float, float]] = []
    for w in walls:
        if not w.is_vertical:
            continue
        wx = (w.p1[0] + w.p2[0]) / 2.0
        if abs(wx - target_x) > axis_tol:
            continue
        lo, hi = sorted((w.p1[1], w.p2[1]))
        clipped_lo = max(lo, polygon_miny)
        clipped_hi = min(hi, polygon_maxy)
        if clipped_hi > clipped_lo:
            intervals.append((clipped_lo, clipped_hi))
    if not intervals:
        return 0.0
    intervals.sort()
    total = 0.0
    cur_lo, cur_hi = intervals[0]
    for lo, hi in intervals[1:]:
        if lo <= cur_hi:
            cur_hi = max(cur_hi, hi)
        else:
            total += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
    total += cur_hi - cur_lo
    return total


def _collective_overlap_at_y(
    target_y: float,
    walls: list[_WallLine],
    polygon_minx: float, polygon_maxx: float,
    axis_tol: float = _AXIS_GROUP_TOL_M,
) -> float:
    """Sum union of X-overlaps for all horizontal walls within `axis_tol` of `target_y`."""
    intervals: list[tuple[float, float]] = []
    for w in walls:
        if not w.is_horizontal:
            continue
        wy = (w.p1[1] + w.p2[1]) / 2.0
        if abs(wy - target_y) > axis_tol:
            continue
        lo, hi = sorted((w.p1[0], w.p2[0]))
        clipped_lo = max(lo, polygon_minx)
        clipped_hi = min(hi, polygon_maxx)
        if clipped_hi > clipped_lo:
            intervals.append((clipped_lo, clipped_hi))
    if not intervals:
        return 0.0
    intervals.sort()
    total = 0.0
    cur_lo, cur_hi = intervals[0]
    for lo, hi in intervals[1:]:
        if lo <= cur_hi:
            cur_hi = max(cur_hi, hi)
        else:
            total += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
    total += cur_hi - cur_lo
    return total


def _cast_x(
    polygon_minx: float, polygon_maxx: float,
    polygon_miny: float, polygon_maxy: float,
    direction: int,
    walls: list[_WallLine],
    *,
    max_cast_dist_m: float,
) -> float | None:
    """Cast a horizontal ray; return x-coord of closest qualifying vertical wall.

    Aggregates fragments at the same X position via `_collective_overlap_at_x`
    so a wall broken by doors / windows still qualifies as a bound when its
    fragments collectively cover the polygon's perpendicular extent.
    """
    polygon_h = polygon_maxy - polygon_miny
    best_x: float | None = None
    best_gap = max_cast_dist_m
    for w in walls:
        if not w.is_vertical:
            continue
        wall_x = (w.p1[0] + w.p2[0]) / 2.0
        if direction > 0:
            if wall_x <= polygon_maxx:
                continue
            gap = wall_x - polygon_maxx
        else:
            if wall_x >= polygon_minx:
                continue
            gap = polygon_minx - wall_x
        if gap > max_cast_dist_m:
            continue
        overlap = _collective_overlap_at_x(
            wall_x, walls, polygon_miny, polygon_maxy,
        )
        if polygon_h > 0 and overlap < _MIN_PERPENDICULAR_OVERLAP_FRAC * polygon_h:
            continue
        if gap < best_gap:
            best_gap = gap
            best_x = wall_x
    return best_x


def _cast_y(
    polygon_minx: float, polygon_maxx: float,
    polygon_miny: float, polygon_maxy: float,
    direction: int,
    walls: list[_WallLine],
    *,
    max_cast_dist_m: float,
) -> float | None:
    """Cast a vertical ray; return y-coord of closest qualifying horizontal wall.

    Same aggregation as `_cast_x` along the Y axis.
    """
    polygon_w = polygon_maxx - polygon_minx
    best_y: float | None = None
    best_gap = max_cast_dist_m
    for w in walls:
        if not w.is_horizontal:
            continue
        wall_y = (w.p1[1] + w.p2[1]) / 2.0
        if direction > 0:
            if wall_y <= polygon_maxy:
                continue
            gap = wall_y - polygon_maxy
        else:
            if wall_y >= polygon_miny:
                continue
            gap = polygon_miny - wall_y
        if gap > max_cast_dist_m:
            continue
        overlap = _collective_overlap_at_y(
            wall_y, walls, polygon_minx, polygon_maxx,
        )
        if polygon_w > 0 and overlap < _MIN_PERPENDICULAR_OVERLAP_FRAC * polygon_w:
            continue
        if gap < best_gap:
            best_gap = gap
            best_y = wall_y
    return best_y


def _resolve_axis_translation(
    polygon_lo: float, polygon_hi: float,
    wall_lo: float | None, wall_hi: float | None,
    *,
    has_adjacent_room_lo: bool = True,
    has_adjacent_room_hi: bool = True,
    significant_gap_m: float = _MIN_SIGNIFICANT_GAP_M,
) -> float:
    """Compute one-axis translation from wall-cast results.

    `has_adjacent_room_*` flags say whether another room sits beyond the
    discovered wall on that side. The principle "rooms must be contiguous"
    means we only push polygon edges toward walls that have a room on the
    far side — those are interior partitions the polygon SHOULD touch.
    Walls with no room beyond are exterior boundaries; we don't trust them
    as translation targets because they're often unrelated to where the
    polygon's labelled dimensions say its edge belongs.

    Both walls + matching polygon width → center the polygon between them.
    Both walls + polygon smaller:
        - If one side's gap is below `significant_gap_m`, the polygon is
          essentially at that wall. Push the OTHER side toward its wall,
          but ONLY if that side has an adjacent room (else don't move).
        - Otherwise both sides have a real gap; pick the smaller-move option
          biased toward the side with an adjacent room when only one has it.
    One wall → translate polygon's nearest edge to touch it, only when an
      adjacent room exists beyond that wall.
    Neither → 0.
    """
    if wall_lo is None and wall_hi is None:
        return 0.0
    if wall_lo is not None and wall_hi is not None:
        polygon_width = polygon_hi - polygon_lo
        wall_width = wall_hi - wall_lo
        # Center only when BOTH walls are interior partitions. If one side
        # is exterior (no room beyond), centering pushes polygon away from
        # an interior boundary it should align with toward an unrelated
        # wall — wrong. Fall through to align-with-interior logic instead.
        fits_between = wall_width > 0 and 0.85 <= polygon_width / wall_width <= 1.15
        if fits_between and has_adjacent_room_lo and has_adjacent_room_hi:
            target_center = (wall_lo + wall_hi) / 2.0
            polygon_center = (polygon_lo + polygon_hi) / 2.0
            return target_center - polygon_center
        gap_lo = polygon_lo - wall_lo
        gap_hi = wall_hi - polygon_hi
        # Asymmetric phantom-gap rule, refined for adjacency. The "polygon
        # already at wall on one side" pattern only justifies pushing toward
        # the other side if that other side has a room beyond it.
        if gap_lo < significant_gap_m <= gap_hi:
            return gap_hi if has_adjacent_room_hi else 0.0
        if gap_hi < significant_gap_m <= gap_lo:
            return -gap_lo if has_adjacent_room_lo else 0.0
        # Both sides have meaningful gap. Prefer the side with an adjacent
        # room. If both or neither have one, pick the smaller move.
        if has_adjacent_room_lo and not has_adjacent_room_hi:
            return -gap_lo
        if has_adjacent_room_hi and not has_adjacent_room_lo:
            return gap_hi
        if gap_lo < gap_hi:
            return -gap_lo
        return gap_hi
    if wall_lo is not None:
        if not has_adjacent_room_lo:
            return 0.0
        gap = polygon_lo - wall_lo
        return -gap if gap > 0 else 0.0
    assert wall_hi is not None
    if not has_adjacent_room_hi:
        return 0.0
    gap = wall_hi - polygon_hi
    return gap if gap > 0 else 0.0


def _has_adjacent_room_beyond_wall_x(
    wall_x: float,
    direction: int,
    polygon_miny: float, polygon_maxy: float,
    room: Room,
    other_rooms: list[Room],
    *,
    max_search_m: float = _MAX_CAST_DIST_M,
) -> bool:
    """Is there a same-floor other room whose center is beyond wall_x in the
    cast direction, with Y range overlapping the polygon's Y extent, within
    `max_search_m` of wall_x? Such a room makes wall_x an interior partition
    rather than an exterior boundary.
    """
    for other in other_rooms:
        if other.id == room.id or other.floor_level != room.floor_level:
            continue
        ox = [p.x for p in other.polygon]
        oy = [p.y for p in other.polygon]
        other_minx, other_maxx = min(ox), max(ox)
        other_miny, other_maxy = min(oy), max(oy)
        other_cx = (other_minx + other_maxx) / 2.0
        # On correct side of wall?
        if direction > 0:
            if other_cx <= wall_x:
                continue
            dist = other_minx - wall_x
        else:
            if other_cx >= wall_x:
                continue
            dist = wall_x - other_maxx
        if dist > max_search_m:
            continue
        # Y overlap with polygon?
        overlap_lo = max(other_miny, polygon_miny)
        overlap_hi = min(other_maxy, polygon_maxy)
        if overlap_hi - overlap_lo <= 0.5:   # need >0.5m perpendicular overlap
            continue
        return True
    return False


def _has_adjacent_room_beyond_wall_y(
    wall_y: float,
    direction: int,
    polygon_minx: float, polygon_maxx: float,
    room: Room,
    other_rooms: list[Room],
    *,
    max_search_m: float = _MAX_CAST_DIST_M,
) -> bool:
    """Same as the X version, transposed for horizontal walls."""
    for other in other_rooms:
        if other.id == room.id or other.floor_level != room.floor_level:
            continue
        ox = [p.x for p in other.polygon]
        oy = [p.y for p in other.polygon]
        other_minx, other_maxx = min(ox), max(ox)
        other_miny, other_maxy = min(oy), max(oy)
        other_cy = (other_miny + other_maxy) / 2.0
        if direction > 0:
            if other_cy <= wall_y:
                continue
            dist = other_miny - wall_y
        else:
            if other_cy >= wall_y:
                continue
            dist = wall_y - other_maxy
        if dist > max_search_m:
            continue
        overlap_lo = max(other_minx, polygon_minx)
        overlap_hi = min(other_maxx, polygon_maxx)
        if overlap_hi - overlap_lo <= 0.5:
            continue
        return True
    return False


def cast_bounding_walls(
    room: Room,
    wall_segments: list[Segment],
    *,
    other_rooms: list[Room] | None = None,
    max_cast_dist_m: float = _MAX_CAST_DIST_M,
    min_significant_gap_m: float = _MIN_SIGNIFICANT_GAP_M,
    max_translation_m: float = _MAX_TRANSLATION_M,
) -> Room:
    """Translate room polygon to its bounding walls. Returns new Room or input.

    If `other_rooms` is given, any translation that would introduce a new
    overlap with another room's footprint (above a small tolerance for
    pre-existing borderline overlaps) is rejected — the room is returned
    unchanged. This prevents wall-cast from pushing one room wholesale into
    another's space when it finds the wrong wall.
    """
    polygon = room.polygon
    if len(polygon) < 3 or not wall_segments:
        return room
    walls = _build_walls(wall_segments)
    if not walls:
        return room
    minx, miny, maxx, maxy = _polygon_bbox(polygon)
    wall_left = _cast_x(
        minx, maxx, miny, maxy, direction=-1, walls=walls,
        max_cast_dist_m=max_cast_dist_m,
    )
    wall_right = _cast_x(
        minx, maxx, miny, maxy, direction=+1, walls=walls,
        max_cast_dist_m=max_cast_dist_m,
    )
    wall_down = _cast_y(
        minx, maxx, miny, maxy, direction=-1, walls=walls,
        max_cast_dist_m=max_cast_dist_m,
    )
    wall_up = _cast_y(
        minx, maxx, miny, maxy, direction=+1, walls=walls,
        max_cast_dist_m=max_cast_dist_m,
    )
    # Adjacent-room presence per direction. When the caller doesn't pass
    # `other_rooms`, we don't have the context to check, so we trust the wall
    # as-is (preserves single-room test semantics). When other_rooms IS
    # provided, we gate translation on whether each wall is an interior
    # partition (has a room beyond it) or just an exterior boundary.
    if other_rooms is None:
        has_adj_left = has_adj_right = has_adj_down = has_adj_up = True
    else:
        has_adj_left = wall_left is not None and _has_adjacent_room_beyond_wall_x(
            wall_left, -1, miny, maxy, room, other_rooms,
            max_search_m=max_cast_dist_m,
        )
        has_adj_right = wall_right is not None and _has_adjacent_room_beyond_wall_x(
            wall_right, +1, miny, maxy, room, other_rooms,
            max_search_m=max_cast_dist_m,
        )
        has_adj_down = wall_down is not None and _has_adjacent_room_beyond_wall_y(
            wall_down, -1, minx, maxx, room, other_rooms,
            max_search_m=max_cast_dist_m,
        )
        has_adj_up = wall_up is not None and _has_adjacent_room_beyond_wall_y(
            wall_up, +1, minx, maxx, room, other_rooms,
            max_search_m=max_cast_dist_m,
        )
    dx = _resolve_axis_translation(
        minx, maxx, wall_left, wall_right,
        has_adjacent_room_lo=has_adj_left,
        has_adjacent_room_hi=has_adj_right,
        significant_gap_m=min_significant_gap_m,
    )
    dy = _resolve_axis_translation(
        miny, maxy, wall_down, wall_up,
        has_adjacent_room_lo=has_adj_down,
        has_adjacent_room_hi=has_adj_up,
        significant_gap_m=min_significant_gap_m,
    )
    # Zero out small components — those are the snap step's job.
    if abs(dx) < min_significant_gap_m:
        dx = 0.0
    if abs(dy) < min_significant_gap_m:
        dy = 0.0
    if dx == 0.0 and dy == 0.0:
        return room
    # Hard safety cap.
    if abs(dx) > max_translation_m or abs(dy) > max_translation_m:
        return room
    new_polygon = [Point(x=p.x + dx, y=p.y + dy) for p in polygon]
    # Overlap guard: reject any translation that creates a NEW overlap (or
    # increases an existing borderline one) with another room. We compare
    # against `other_rooms` original positions — a single pass, no
    # ordering-dependent interactions.
    if other_rooms and _translation_creates_overlap(
        room, polygon, new_polygon, other_rooms,
    ):
        # The primary translation makes overlap worse. If the polygon is
        # CURRENTLY overlapping another room, try the OPPOSITE direction —
        # the wall-cast results give us walls on both sides, so flipping
        # the sign may give a polygon that escapes the existing overlap.
        if other_rooms and _has_room_overlap(room, polygon, other_rooms):
            # Find the candidate that minimizes overlap area. Prefer real
            # moves over no-op so we don't silently keep the overlapping
            # state when a wall-cast option could escape it.
            best_polygon: list[Point] | None = None
            best_overlap = _total_overlap_area(room, polygon, other_rooms)
            alt_dx_options = _opposite_axis_options(
                polygon_lo=minx, polygon_hi=maxx,
                wall_lo=wall_left, wall_hi=wall_right,
                current_dx=dx, significant_gap_m=min_significant_gap_m,
            )
            alt_dy_options = _opposite_axis_options(
                polygon_lo=miny, polygon_hi=maxy,
                wall_lo=wall_down, wall_hi=wall_up,
                current_dx=dy, significant_gap_m=min_significant_gap_m,
            )
            for cand_dx in alt_dx_options:
                for cand_dy in alt_dy_options:
                    if abs(cand_dx) > max_translation_m or abs(cand_dy) > max_translation_m:
                        continue
                    if cand_dx == 0.0 and cand_dy == 0.0:
                        continue
                    cand_polygon = [Point(x=p.x + cand_dx, y=p.y + cand_dy) for p in polygon]
                    cand_overlap = _total_overlap_area(room, cand_polygon, other_rooms)
                    if cand_overlap < best_overlap - 0.1:
                        best_overlap = cand_overlap
                        best_polygon = cand_polygon
            if best_polygon is not None:
                return room.model_copy(update={"polygon": best_polygon})
        return room
    return room.model_copy(update={"polygon": new_polygon})


def _has_room_overlap(
    room: Room, polygon: list[Point], other_rooms: list[Room],
) -> bool:
    """Does the room currently overlap any other same-floor room by more than tol?"""
    return _total_overlap_area(room, polygon, other_rooms) > 0.1


def _total_overlap_area(
    room: Room, polygon: list[Point], other_rooms: list[Room],
) -> float:
    """Total area in square metres that `polygon` overlaps any other same-floor room."""
    try:
        shape = ShapelyPolygon([(p.x, p.y) for p in polygon])
    except (ValueError, TypeError):
        return 0.0
    if not shape.is_valid:
        return 0.0
    total = 0.0
    for other in other_rooms:
        if other.id == room.id or other.floor_level != room.floor_level:
            continue
        try:
            other_shape = ShapelyPolygon([(p.x, p.y) for p in other.polygon])
        except (ValueError, TypeError):
            continue
        if not other_shape.is_valid:
            continue
        total += shape.intersection(other_shape).area
    return total


def _opposite_axis_options(
    *,
    polygon_lo: float, polygon_hi: float,
    wall_lo: float | None, wall_hi: float | None,
    current_dx: float,
    significant_gap_m: float,
) -> list[float]:
    """Possible alternative translations on one axis: 0 (no move), push to
    wall_lo, push to wall_hi. Skip moves below the significant-gap threshold.
    """
    out: list[float] = [0.0]
    if wall_lo is not None:
        delta = wall_lo - polygon_lo
        if abs(delta) >= significant_gap_m:
            out.append(delta)
    if wall_hi is not None:
        delta = wall_hi - polygon_hi
        if abs(delta) >= significant_gap_m:
            out.append(delta)
    return out


def _translation_creates_overlap(
    room: Room,
    old_polygon: list[Point],
    new_polygon: list[Point],
    other_rooms: list[Room],
) -> bool:
    """Return True iff `new_polygon` overlaps any other room by more than the
    original polygon did (i.e. the move would WORSEN overlap).

    Same-floor only — rooms on different floor_level are physically stacked
    and can occupy the same X/Y region without conflict.
    """
    try:
        old_shape = ShapelyPolygon([(p.x, p.y) for p in old_polygon])
        new_shape = ShapelyPolygon([(p.x, p.y) for p in new_polygon])
    except (ValueError, TypeError):
        return True   # degenerate, bail
    if not new_shape.is_valid:
        return True
    tol = 0.1   # 0.1 sqm slack for floating-point noise
    for other in other_rooms:
        if other.id == room.id or other.floor_level != room.floor_level:
            continue
        try:
            other_shape = ShapelyPolygon([(p.x, p.y) for p in other.polygon])
        except (ValueError, TypeError):
            continue
        if not other_shape.is_valid:
            continue
        new_overlap = new_shape.intersection(other_shape).area
        old_overlap = old_shape.intersection(other_shape).area
        if new_overlap - old_overlap > tol:
            return True
    return False


def cast_bounding_walls_for_rooms(
    rooms: list[Room],
    wall_segments: list[Segment],
    *,
    max_cast_dist_m: float = _MAX_CAST_DIST_M,
    min_significant_gap_m: float = _MIN_SIGNIFICANT_GAP_M,
    max_translation_m: float = _MAX_TRANSLATION_M,
) -> tuple[list[Room], int]:
    """Apply `cast_bounding_walls` to every room. Returns (rooms, translated_count).

    Each room is checked against the ORIGINAL positions of every other room
    (single-pass, no ordering interaction). A translation that would create a
    new overlap with any other room is rejected.
    """
    out: list[Room] = []
    translated = 0
    for r in rooms:
        new_r = cast_bounding_walls(
            r, wall_segments,
            other_rooms=rooms,
            max_cast_dist_m=max_cast_dist_m,
            min_significant_gap_m=min_significant_gap_m,
            max_translation_m=max_translation_m,
        )
        if new_r.polygon != r.polygon:
            translated += 1
        out.append(new_r)
    return out, translated
