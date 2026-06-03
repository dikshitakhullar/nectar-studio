"""Snap room polygon edges to real wall lines to eliminate phantom gaps.

After label-based placement, each room polygon is correctly *positioned* but
its edges only approximate the architect's actual wall lines (the polygon's
dimensions come from the room label, not the walls). Two adjacent rooms can
therefore each declare an edge that sits a few centimetres away from the same
shared wall — leaving an empty strip between them in the rendered plan.

Walls are the source of truth. For each room edge we look for a nearby wall
segment that is plausibly the same wall (close, parallel, with substantial
overlap) and re-project the edge endpoints onto that wall's infinite line. When
two adjacent rooms each snap their facing edges to the SAME wall, they now
share that wall exactly — the phantom gap disappears as a side-effect.

Coordinates throughout this module are in local-meter frame (matching the Room
polygon convention). The caller converts DXF-unit wall segments to local
meters before calling `snap_room_to_walls`.
"""

import math
from dataclasses import dataclass

from lighting_engine.models.geometry import Point, Room

Segment = tuple[tuple[float, float], tuple[float, float]]

# --- Tunable thresholds ----------------------------------------------------
# Perpendicular distance from edge midpoint to wall infinite line, in meters.
# Indian residential walls are ~0.23m thick; 0.8m allows snapping across a wall
# thickness plus a small mis-position.
_MAX_PERP_DIST_M = 0.8
# Angle between edge direction and wall direction; allows for off-square rooms
# without snapping a vertical edge to a horizontal wall.
_MAX_PARALLEL_DEG = 15.0
# Fraction of the edge length that must be overlapped by the wall (projected
# onto the wall's direction). 0.5 = wall must cover at least half of the edge.
_MIN_OVERLAP_FRAC = 0.5
# Reject the whole snap for this room if the snapped polygon's area changed by
# more than this fraction — that means we deformed the room badly (e.g. snapped
# two opposite edges onto walls that pinch it).
_MAX_AREA_DEFORM_FRAC = 0.15


@dataclass(frozen=True)
class _WallLine:
    """Pre-computed wall geometry for fast candidate matching."""

    p1: tuple[float, float]
    p2: tuple[float, float]
    # Unit direction vector along the wall
    dx: float
    dy: float
    length: float


def _build_wall_lines(segments: list[Segment]) -> list[_WallLine]:
    out: list[_WallLine] = []
    for (x1, y1), (x2, y2) in segments:
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0.0:
            continue
        out.append(_WallLine(
            p1=(x1, y1),
            p2=(x2, y2),
            dx=(x2 - x1) / length,
            dy=(y2 - y1) / length,
            length=length,
        ))
    return out


def _angle_between_deg(
    e_dx: float, e_dy: float, w_dx: float, w_dy: float,
) -> float:
    """Smallest angle between two undirected line directions, in degrees [0, 90]."""
    # Use dot of unit vectors; |cos| folds direction-reversal into the same line.
    cos = abs(e_dx * w_dx + e_dy * w_dy)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))


def _perp_distance_point_to_line(
    px: float, py: float, wall: _WallLine,
) -> float:
    """Perpendicular distance from (px, py) to the infinite line through wall."""
    # |(p - p1) x dir|
    vx = px - wall.p1[0]
    vy = py - wall.p1[1]
    return abs(vx * wall.dy - vy * wall.dx)


def _project_param(
    px: float, py: float, wall: _WallLine,
) -> float:
    """Signed distance from wall.p1 to the foot of perpendicular from p, along wall direction."""
    vx = px - wall.p1[0]
    vy = py - wall.p1[1]
    return vx * wall.dx + vy * wall.dy


def _project_point_onto_line(
    px: float, py: float, wall: _WallLine,
) -> tuple[float, float]:
    """Perpendicular projection of (px, py) onto the infinite line through wall."""
    t = _project_param(px, py, wall)
    return (wall.p1[0] + t * wall.dx, wall.p1[1] + t * wall.dy)


def _overlap_fraction(
    ax: float, ay: float, bx: float, by: float, wall: _WallLine,
) -> float:
    """Fraction of the edge (a → b) that overlaps the wall when projected onto wall dir.

    Returns intersection_length / edge_length. 0 = no overlap, 1 = wall fully
    covers the edge along its own direction.
    """
    edge_len = math.hypot(bx - ax, by - ay)
    if edge_len <= 0.0:
        return 0.0
    t_a = _project_param(ax, ay, wall)
    t_b = _project_param(bx, by, wall)
    e_lo, e_hi = (t_a, t_b) if t_a <= t_b else (t_b, t_a)
    # Wall spans [0, wall.length] in wall-direction parameter
    w_lo, w_hi = 0.0, wall.length
    inter = max(0.0, min(e_hi, w_hi) - max(e_lo, w_lo))
    return inter / edge_len


def _find_best_wall(
    a: Point, b: Point, walls: list[_WallLine],
    *,
    max_perp: float,
    max_angle_deg: float,
    min_overlap: float,
) -> _WallLine | None:
    """Pick the wall closest (perpendicular distance) to the edge midpoint
    among those passing the parallel + overlap thresholds. None if none qualify.
    """
    edge_dx = b.x - a.x
    edge_dy = b.y - a.y
    edge_len = math.hypot(edge_dx, edge_dy)
    if edge_len <= 0.0:
        return None
    e_ux = edge_dx / edge_len
    e_uy = edge_dy / edge_len
    mx = (a.x + b.x) / 2
    my = (a.y + b.y) / 2

    best: _WallLine | None = None
    best_perp = float("inf")
    for w in walls:
        if _angle_between_deg(e_ux, e_uy, w.dx, w.dy) > max_angle_deg:
            continue
        perp = _perp_distance_point_to_line(mx, my, w)
        if perp > max_perp:
            continue
        if _overlap_fraction(a.x, a.y, b.x, b.y, w) < min_overlap:
            continue
        if perp < best_perp:
            best_perp = perp
            best = w
    return best


def _line_intersection(
    p1: tuple[float, float], d1: tuple[float, float],
    p2: tuple[float, float], d2: tuple[float, float],
) -> tuple[float, float] | None:
    """Intersect two infinite lines (point + unit direction). None if parallel."""
    det = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(det) < 1e-9:
        return None
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    t = (dx * d2[1] - dy * d2[0]) / det
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])


def _polygon_area(polygon: list[Point]) -> float:
    """Shoelace area (unsigned) for the polygon."""
    n = len(polygon)
    s = 0.0
    for i in range(n):
        x1, y1 = polygon[i].x, polygon[i].y
        x2, y2 = polygon[(i + 1) % n].x, polygon[(i + 1) % n].y
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def snap_room_to_walls(
    room: Room,
    wall_segments: list[Segment],
    *,
    max_perp_dist_m: float = _MAX_PERP_DIST_M,
    max_parallel_deg: float = _MAX_PARALLEL_DEG,
    min_overlap_frac: float = _MIN_OVERLAP_FRAC,
    max_area_deform_frac: float = _MAX_AREA_DEFORM_FRAC,
) -> Room:
    """Snap each polygon edge to the nearest qualifying wall line.

    Pure function. Returns a new Room with the snapped polygon, or the input
    Room unchanged if snapping would deform the polygon's area by more than
    `max_area_deform_frac`.

    Algorithm (per edge):
      1. Find wall candidates that are within `max_perp_dist_m` (perpendicular
         distance from the edge midpoint to the wall's infinite line),
         parallel within `max_parallel_deg`, and overlap the edge by at least
         `min_overlap_frac` of the edge length.
      2. Pick the candidate with the smallest perpendicular distance.
      3. Replace the edge with the perpendicular projection of both endpoints
         onto that wall's infinite line.

    After all edges are snapped, the corners are recomputed by intersecting
    each pair of adjacent edge lines (preserves orthogonality where adjacent
    edges snapped to perpendicular walls). When the lines are parallel the
    original corner is kept.
    """
    polygon = room.polygon
    n = len(polygon)
    if n < 3 or not wall_segments:
        return room

    walls = _build_wall_lines(wall_segments)
    if not walls:
        return room

    # Pre-compute each edge's candidate wall (or None).
    # `edge_data[i]` corresponds to edge i → i+1 in the polygon.
    @dataclass(frozen=True)
    class _EdgeData:
        # Origin point of the (possibly snapped) edge line
        origin: tuple[float, float]
        # Unit direction vector along the edge line
        direction: tuple[float, float]
        snapped: bool

    edge_data: list[_EdgeData] = []
    any_snapped = False
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        wall = _find_best_wall(
            a, b, walls,
            max_perp=max_perp_dist_m,
            max_angle_deg=max_parallel_deg,
            min_overlap=min_overlap_frac,
        )
        if wall is None:
            edge_len = math.hypot(b.x - a.x, b.y - a.y)
            if edge_len <= 0.0:
                return room  # degenerate — bail
            edge_data.append(_EdgeData(
                origin=(a.x, a.y),
                direction=((b.x - a.x) / edge_len, (b.y - a.y) / edge_len),
                snapped=False,
            ))
            continue
        # Project both endpoints onto the wall's infinite line. The new edge
        # line is the wall's line (origin = projected-a, direction = wall.dir).
        a_proj = _project_point_onto_line(a.x, a.y, wall)
        edge_data.append(_EdgeData(
            origin=a_proj,
            direction=(wall.dx, wall.dy),
            snapped=True,
        ))
        any_snapped = True

    if not any_snapped:
        return room

    # Reconstruct corners by intersecting adjacent edge lines.
    new_polygon: list[Point] = []
    for i in range(n):
        prev_edge = edge_data[(i - 1) % n]
        this_edge = edge_data[i]
        intersection = _line_intersection(
            prev_edge.origin, prev_edge.direction,
            this_edge.origin, this_edge.direction,
        )
        if intersection is None:
            # Adjacent edges parallel — fall back to the original corner.
            new_polygon.append(polygon[i])
        else:
            new_polygon.append(Point(x=intersection[0], y=intersection[1]))

    # Validate: area deformation guard.
    orig_area = _polygon_area(polygon)
    new_area = _polygon_area(new_polygon)
    if orig_area <= 0.0:
        return room
    if abs(new_area - orig_area) / orig_area > max_area_deform_frac:
        return room

    return room.model_copy(update={"polygon": new_polygon})


def snap_rooms_to_walls(
    rooms: list[Room],
    wall_segments: list[Segment],
    *,
    max_perp_dist_m: float = _MAX_PERP_DIST_M,
    max_parallel_deg: float = _MAX_PARALLEL_DEG,
    min_overlap_frac: float = _MIN_OVERLAP_FRAC,
    max_area_deform_frac: float = _MAX_AREA_DEFORM_FRAC,
) -> tuple[list[Room], int, int]:
    """Apply `snap_room_to_walls` to every room.

    Returns (rooms, snapped_count, rejected_count). `snapped_count` is the
    number of rooms whose polygon actually changed; `rejected_count` is the
    number of rooms where snapping *would* have moved the polygon but was
    rejected by the area-deformation guard (the room is returned unchanged).
    """
    out: list[Room] = []
    snapped = 0
    rejected = 0
    walls = _build_wall_lines(wall_segments)
    for r in rooms:
        new_r = snap_room_to_walls(
            r, wall_segments,
            max_perp_dist_m=max_perp_dist_m,
            max_parallel_deg=max_parallel_deg,
            min_overlap_frac=min_overlap_frac,
            max_area_deform_frac=max_area_deform_frac,
        )
        if new_r.polygon != r.polygon:
            snapped += 1
        else:
            # Polygon unchanged — was that because no edge had a candidate, or
            # because the area-deformation guard fired?
            had_candidate = any(
                _find_best_wall(
                    r.polygon[i], r.polygon[(i + 1) % len(r.polygon)], walls,
                    max_perp=max_perp_dist_m,
                    max_angle_deg=max_parallel_deg,
                    min_overlap=min_overlap_frac,
                ) is not None
                for i in range(len(r.polygon))
            )
            if had_candidate:
                rejected += 1
        out.append(new_r)
    return out, snapped, rejected
