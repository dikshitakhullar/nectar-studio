"""Infer the destination room for each door.

Each :class:`Door` carries ``wall_index`` + ``along_wall`` — enough to locate
the door's centre on the host room's polygon edge. To find what the door
*leads to*, we step a short distance along the wall's outward normal (pointing
away from the host room's centroid) and ask which OTHER room's polygon
contains that exterior point. That room becomes the door's
``destination_room_id``.

This is intentionally a pure function. No I/O, no parser state, no mutation
beyond the door fields themselves. The caller (``parser/pipeline.parse_file``)
wires it in after entity attachment so doors have valid wall indices by then.

Doors with no detected wall (``wall_index is None``) and doors whose outward
step lands in no room (true exterior doors — balcony, main entrance) leave
``destination_room_id`` as ``None``.
"""

import math

from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.models.geometry import Door, Point, Room

# How far past the wall to look for the adjacent room (meters). Big enough to
# clear typical wall thickness (~0.2–0.25m for brick partitions in residential
# plans) and any rounding noise from the polygon edge, but small enough that
# we don't accidentally hop across a corridor into the room beyond. Tuned
# against the Delhi fixture.
_OUTWARD_STEP_M = 0.3


def infer_door_destinations(rooms: list[Room]) -> None:
    """Mutate ``rooms`` in place: for each door, set ``destination_room_id``
    based on the room sitting on the OTHER side of the wall the door is on.

    Doors with no adjacent room (exterior doors to balconies / outside) leave
    ``destination_room_id`` as ``None``. Doors whose ``wall_index`` is ``None``
    are skipped — the parser couldn't snap them to a specific wall, so we can't
    determine a destination.

    Idempotent: re-running on already-annotated doors recomputes the same
    destinations.
    """
    if not rooms:
        return

    # Pre-build shapely polygons keyed by index. We pair them with the host
    # rooms so we can compare ids and skip the door's own room.
    room_polys: list[ShapelyPolygon] = [
        ShapelyPolygon([(p.x, p.y) for p in r.polygon]) for r in rooms
    ]

    for host_room in rooms:
        for door in host_room.doors:
            destination = _infer_one_destination(
                door=door,
                host_room=host_room,
                rooms=rooms,
                room_polys=room_polys,
            )
            door.destination_room_id = destination


def _infer_one_destination(
    *,
    door: Door,
    host_room: Room,
    rooms: list[Room],
    room_polys: list[ShapelyPolygon],
) -> str | None:
    """Return the destination room id for a single door, or ``None`` if it
    sits on an exterior wall or can't be located."""
    if door.wall_index is None or door.along_wall is None:
        return None
    polygon = host_room.polygon
    n = len(polygon)
    if door.wall_index < 0 or door.wall_index >= n:
        return None

    a = polygon[door.wall_index]
    b = polygon[(door.wall_index + 1) % n]
    # Door centre along the wall edge
    door_x = a.x + (b.x - a.x) * door.along_wall
    door_y = a.y + (b.y - a.y) * door.along_wall

    # Outward normal: rotate edge direction (dx, dy) by 90°, then flip if it
    # points toward the polygon centroid rather than away.
    edge_dx = b.x - a.x
    edge_dy = b.y - a.y
    edge_len = math.hypot(edge_dx, edge_dy)
    if edge_len <= 0.0:
        return None
    # Two candidate perpendiculars: (-edge_dy, edge_dx) and (edge_dy, -edge_dx).
    # Pick the one pointing AWAY from the centroid.
    nx = -edge_dy / edge_len
    ny = edge_dx / edge_len
    cx, cy = _polygon_centroid(polygon)
    # Vector from edge midpoint toward centroid
    mid_x = (a.x + b.x) / 2.0
    mid_y = (a.y + b.y) / 2.0
    to_centroid_x = cx - mid_x
    to_centroid_y = cy - mid_y
    # If the candidate normal points the same way as the to-centroid vector
    # (dot product > 0), we're pointing INWARD — flip.
    if nx * to_centroid_x + ny * to_centroid_y > 0.0:
        nx = -nx
        ny = -ny

    probe_x = door_x + nx * _OUTWARD_STEP_M
    probe_y = door_y + ny * _OUTWARD_STEP_M
    probe = ShapelyPoint(probe_x, probe_y)

    for other_room, other_poly in zip(rooms, room_polys, strict=True):
        if other_room.id == host_room.id:
            continue
        if other_poly.contains(probe):
            return other_room.id
    return None


def _polygon_centroid(polygon: list[Point]) -> tuple[float, float]:
    """Vertex-average centroid. Adequate for the inward/outward normal test —
    we only need a point inside the polygon. Even for mildly concave room
    polygons the vertex average still falls inside, and the test only needs
    the sign of the dot product to be right.
    """
    n = len(polygon)
    sx = sum(p.x for p in polygon)
    sy = sum(p.y for p in polygon)
    return sx / n, sy / n
