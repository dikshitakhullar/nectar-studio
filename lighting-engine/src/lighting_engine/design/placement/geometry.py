"""Polygon + edge math used by placement rules.

Kept separate from the rules themselves so each rule reads as design
intent, not vector arithmetic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from lighting_engine.models.geometry import Point, Room


@dataclass(frozen=True)
class WallEdge:
    """One polygon edge with its midpoint + outward normal pre-computed."""
    index: int
    a: Point
    b: Point
    midpoint: Point
    length_m: float
    outward_nx: float
    outward_ny: float


def polygon_centroid(polygon: list[Point]) -> Point:
    n = len(polygon)
    return Point(
        x=sum(p.x for p in polygon) / n,
        y=sum(p.y for p in polygon) / n,
    )


def wall_edges(room: Room) -> list[WallEdge]:
    """Return one WallEdge per polygon edge of the room."""
    if not room.polygon:
        return []
    polygon = room.polygon
    centroid = polygon_centroid(polygon)
    edges: list[WallEdge] = []
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        ex, ey = b.x - a.x, b.y - a.y
        length = math.hypot(ex, ey)
        if length == 0.0:
            continue  # degenerate edge
        # Outward normal (perpendicular to edge, pointing away from centroid)
        nx, ny = -ey / length, ex / length
        mid_x = (a.x + b.x) / 2
        mid_y = (a.y + b.y) / 2
        if (mid_x - centroid.x) * nx + (mid_y - centroid.y) * ny < 0:
            nx, ny = -nx, -ny
        edges.append(WallEdge(
            index=i,
            a=a,
            b=b,
            midpoint=Point(x=mid_x, y=mid_y),
            length_m=length,
            outward_nx=nx,
            outward_ny=ny,
        ))
    return edges


def offset_into_room(edge: WallEdge, distance_m: float) -> Point:
    """Return the point ``distance_m`` inside the room from the edge midpoint."""
    return Point(
        x=edge.midpoint.x - edge.outward_nx * distance_m,
        y=edge.midpoint.y - edge.outward_ny * distance_m,
    )


def evenly_spaced_along_edge(
    edge: WallEdge, *, count: int, inset_m: float = 0.4,
) -> list[Point]:
    """Centred spacing — first and last sit `step/2` from the corner."""
    if count <= 0:
        return []
    usable = max(edge.length_m - 2 * inset_m, 0.0)
    if usable == 0.0 or count == 1:
        return [edge.midpoint]
    step = usable / count
    ex = edge.b.x - edge.a.x
    ey = edge.b.y - edge.a.y
    ux, uy = ex / edge.length_m, ey / edge.length_m
    start_x = edge.a.x + ux * inset_m
    start_y = edge.a.y + uy * inset_m
    return [
        Point(x=start_x + ux * step * (i + 0.5),
              y=start_y + uy * step * (i + 0.5))
        for i in range(count)
    ]


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    """Ray-cast point-in-polygon test (handles concave polygons)."""
    if len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        pi, pj = polygon[i], polygon[j]
        if ((pi.y > point.y) != (pj.y > point.y)):
            x_intersect = (
                (pj.x - pi.x) * (point.y - pi.y) / (pj.y - pi.y) + pi.x
            )
            if point.x < x_intersect:
                inside = not inside
        j = i
    return inside
