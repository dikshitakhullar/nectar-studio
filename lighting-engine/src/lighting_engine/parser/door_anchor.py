"""Bias room polygons toward their detected doors.

After wall-cast + wall-snap, most room polygons are correctly positioned to
within a few centimetres of the architect's actual walls. A small minority
end up far from one of their detected doors — typically a room with weak
wall-cast signal (no qualifying perpendicular wall on one axis, or wall-snap
declined to move because its edges weren't close enough). Doors are a strong
positional anchor: they're drawn precisely so contractors can build to them,
and each door physically belongs to exactly one wall of one room. When a
detected door sits more than 0.4m outside its host room's polygon, the
polygon is in the wrong place — shift it.

This pass is INTENTIONALLY MINIMAL. It only translates (preserves size) and
only when an overlap guard accepts the move. A full multi-signal anchor
solver — combining doors + windows + corner labels into a least-squares
position — is v0.5+ scope.

Coordinates are in the local-meter frame matching `Room.polygon`. Door raw
positions are collected by `parser/door_detection.collect_door_positions`
in the same frame.
"""

import math
from dataclasses import dataclass

from lighting_engine.models.geometry import Point, Room
from lighting_engine.parser.door_detection import DoorRaw
from lighting_engine.parser.wall_cast import (
    _translation_creates_overlap,  # pyright: ignore[reportPrivateUsage]
)

# --- Tunable thresholds ---------------------------------------------------
# Door distance from the polygon perimeter, beyond which we consider the
# polygon misplaced and try to shift it. Matches the existing
# `_DOOR_EDGE_PROXIMITY_M` threshold in `parser/entities.py` (doors farther
# than this are dropped as interior linework, not real doors).
_OFF_PERIMETER_THRESHOLD_M = 0.4
# On-perimeter slack: a door within this distance of the polygon edge is
# considered already-anchored, no translation needed. Smaller than the
# off-threshold so we don't move polygons for noise.
_ON_PERIMETER_TOLERANCE_M = 0.05
# Hard cap on how far we'll move a polygon. Wall-cast uses 6m; door-anchor
# is a smaller-scale correction so 2m is the upper bound here. Beyond this
# we probably matched the door to the wrong room.
_MAX_TRANSLATION_M = 2.0


@dataclass(frozen=True)
class _PerpFoot:
    """Closest point on a polygon edge to a query point, with edge distance."""

    foot: tuple[float, float]
    distance: float
    edge_index: int


def _closest_point_on_polygon(
    polygon: list[Point], point: tuple[float, float],
) -> _PerpFoot:
    """Find the closest point on the polygon's PERIMETER to `point`.

    Walks each edge, projects the query onto the edge (clamped to the edge
    endpoints) and tracks the minimum distance. The polygon is treated as a
    closed loop. Used both to measure how far the door is from the polygon
    and to compute the translation that lands the door on the perimeter.
    """
    px, py = point
    best = _PerpFoot(foot=(px, py), distance=math.inf, edge_index=0)
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        dx = b.x - a.x
        dy = b.y - a.y
        length_sq = dx * dx + dy * dy
        if length_sq <= 0.0:
            continue
        t = ((px - a.x) * dx + (py - a.y) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        fx = a.x + t * dx
        fy = a.y + t * dy
        d = math.hypot(fx - px, fy - py)
        if d < best.distance:
            best = _PerpFoot(foot=(fx, fy), distance=d, edge_index=i)
    return best


def _attach_room_index_for_anchor(
    rooms: list[Room], point: tuple[float, float],
) -> int | None:
    """Pick the room a raw door belongs to using the SAME criteria as
    `parser/entities.attach_room_index`: point-in-polygon (with a 0.05m edge
    slack), else nearest centroid. Returns None when there are no rooms.

    We re-implement the logic here instead of importing from `entities.py`
    because that module imports this one as part of the pipeline order; the
    indirect dependency would force a circular import to share the helper.
    """
    if not rooms:
        return None
    px, py = point
    for i, room in enumerate(rooms):
        if _point_in_or_on_polygon(point, room.polygon, tol=0.05):
            return i
    # Fallback: nearest centroid.
    best_i = 0
    best_d = math.inf
    for i, room in enumerate(rooms):
        xs = [p.x for p in room.polygon]
        ys = [p.y for p in room.polygon]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        d = (cx - px) ** 2 + (cy - py) ** 2
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def _point_in_or_on_polygon(
    point: tuple[float, float], polygon: list[Point], *, tol: float,
) -> bool:
    """Point-in-polygon (ray cast) OR within `tol` meters of perimeter."""
    px, py = point
    n = len(polygon)
    inside = False
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        if (a.y > py) != (b.y > py):
            x_intersect = (b.x - a.x) * (py - a.y) / (b.y - a.y + 1e-12) + a.x
            if px < x_intersect:
                inside = not inside
    if inside:
        return True
    # Within perimeter tolerance?
    return _closest_point_on_polygon(polygon, point).distance <= tol


def _group_doors_by_room(
    rooms: list[Room], raw_doors: list[DoorRaw],
) -> list[list[DoorRaw]]:
    """Assign each raw door to a room using `_attach_room_index_for_anchor`.

    Returns a list parallel to `rooms`, where `out[i]` is every raw door that
    belongs to `rooms[i]`. Mirrors the room-attachment used in
    `attach_entities` so we don't re-route doors between rooms here.
    """
    out: list[list[DoorRaw]] = [[] for _ in rooms]
    for raw in raw_doors:
        idx = _attach_room_index_for_anchor(rooms, raw.position)
        if idx is None:
            continue
        out[idx].append(raw)
    return out


def anchor_polygons_to_doors(
    rooms: list[Room],
    raw_doors: list[DoorRaw],
    *,
    off_perimeter_threshold_m: float = _OFF_PERIMETER_THRESHOLD_M,
    max_translation_m: float = _MAX_TRANSLATION_M,
) -> tuple[list[Room], int]:
    """Translate each room polygon to anchor it to its detected doors.

    Algorithm per room:
      1. Collect raw doors attached to the room (same room-of-best-fit
         used elsewhere — point-in-polygon, nearest-centroid fallback).
      2. Compute each door's perpendicular distance to the polygon perimeter.
      3. Skip the room if every door is within `off_perimeter_threshold_m`
         of the perimeter (polygon already on the doors — no move needed).
      4. Otherwise pick the door with the LARGEST offset (the polygon is
         most clearly out of place there) and compute the translation that
         lands the closest perimeter point on the door. Translation
         preserves polygon size.
      5. Validate via `_translation_creates_overlap` against the ORIGINAL
         positions of every other same-floor room. Reject the move if it
         worsens overlap — single-pass, no order dependence. Log and skip.

    Returns `(rooms, anchored_count)`. `anchored_count` is the number of
    polygons that were actually moved.

    Pure function. Caller is expected to re-run `attach_entities` to
    re-snap doors/windows to the new polygon, so door wall_index /
    along_wall values stay consistent with the polygon edges.
    """
    if not rooms or not raw_doors:
        return rooms, 0

    grouped = _group_doors_by_room(rooms, raw_doors)
    out: list[Room] = []
    anchored = 0
    for ri, room in enumerate(rooms):
        doors = grouped[ri]
        if not doors:
            out.append(room)
            continue
        # Find each door's perpendicular foot on the polygon and its distance.
        feet = [
            (raw, _closest_point_on_polygon(room.polygon, raw.position))
            for raw in doors
        ]
        # Skip when no door is off-perimeter by more than the threshold.
        if max(foot.distance for _, foot in feet) <= off_perimeter_threshold_m:
            out.append(room)
            continue
        # Pick the door with the largest offset to drive the translation.
        worst_raw, worst_foot = max(feet, key=lambda item: item[1].distance)
        dx = worst_raw.position[0] - worst_foot.foot[0]
        dy = worst_raw.position[1] - worst_foot.foot[1]
        # Hard safety cap.
        if abs(dx) > max_translation_m or abs(dy) > max_translation_m:
            out.append(room)
            continue
        if dx == 0.0 and dy == 0.0:
            out.append(room)
            continue
        new_polygon = [Point(x=p.x + dx, y=p.y + dy) for p in room.polygon]
        # Overlap guard against ORIGINAL positions of other rooms (matches
        # the single-pass semantics of `cast_bounding_walls_for_rooms`).
        other_rooms = [r for j, r in enumerate(rooms) if j != ri]
        if _translation_creates_overlap(
            room, room.polygon, new_polygon, other_rooms,
        ):
            out.append(room)
            continue
        out.append(room.model_copy(update={"polygon": new_polygon}))
        anchored += 1
    return out, anchored
