"""Hard constraints applied to every placement attempt.

Each function returns True if the position is SAFE to place a fixture at.
Placement rules call these before adding fixtures to their output list.
"""

from __future__ import annotations

import math

from lighting_engine.design.placement.geometry import (
    point_in_polygon,
    wall_edges,
)
from lighting_engine.design.scene import RoomScene
from lighting_engine.models.geometry import Point, Room

# Minimum distance a fixture must stay from a wall (meters). Matches
# residential downlight install practice — fixtures closer than ~30cm
# from the wall scallop visibly on the wall surface.
_MIN_WALL_OFFSET_M = 0.30


def position_inside_room(position: Point, room: Room) -> bool:
    """True if the position falls inside the room polygon."""
    return point_in_polygon(position, room.polygon)


def position_clear_of_furniture(position: Point, room: Room) -> bool:
    """True if the position is NOT inside any furniture footprint.

    Used to keep downlights off the top of sofas / beds / dining tables.
    Furniture without a footprint polygon is ignored (we have no shape to test).
    """
    for f in room.furniture:
        if not f.footprint or len(f.footprint) < 3:
            continue
        if point_in_polygon(position, f.footprint):
            return False
    return True


def position_min_wall_offset(position: Point, room: Room) -> bool:
    """True if the position is at least `_MIN_WALL_OFFSET_M` from every wall."""
    edges = wall_edges(room)
    for edge in edges:
        ex, ey = edge.b.x - edge.a.x, edge.b.y - edge.a.y
        ax, ay = position.x - edge.a.x, position.y - edge.a.y
        length_sq = ex * ex + ey * ey
        if length_sq == 0:
            continue
        t = max(0.0, min(1.0, (ax * ex + ay * ey) / length_sq))
        closest_x = edge.a.x + t * ex
        closest_y = edge.a.y + t * ey
        dist = math.hypot(position.x - closest_x, position.y - closest_y)
        if dist < _MIN_WALL_OFFSET_M:
            return False
    return True


def wall_has_opening(wall_index: int, room: Room) -> bool:
    """True if the wall has any door or window attached to it."""
    return any(
        opening.wall_index == wall_index
        for opening in (*room.doors, *room.windows)
    )


def wall_purpose(wall_index: int, scene: RoomScene) -> str | None:
    """Return the scene's recorded purpose for `wall_index`, or None."""
    for wp in scene.walls:
        if wp.wall_index == wall_index:
            return wp.purpose
    return None


def safe_for_ceiling_fixture(position: Point, room: Room) -> bool:
    """Combined check: inside the room, off furniture, min wall offset.

    Use this for any ceiling-mounted fixture (downlight, pendant, chandelier).
    Cove strips and wall-mounted fixtures use their own checks.
    """
    return (
        position_inside_room(position, room)
        and position_clear_of_furniture(position, room)
        and position_min_wall_offset(position, room)
    )
