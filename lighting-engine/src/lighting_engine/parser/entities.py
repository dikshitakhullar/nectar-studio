"""Attach walls/windows/doors/furniture/fixtures to the room they belong to.

Walls are not stored on Room directly in v1 (room polygons come from Task 8's
ray-cast wall snapping). Windows, doors, furniture, and fixtures ARE attached.
Each entity is assigned to a Room via shapely point-in-polygon (primary) with
a nearest-centroid fallback for points that sit outside every polygon (e.g. a
balcony fixture on the outside face of a wall).

Coordinates supplied to this module are in DXF units; we convert to meters
in the plan-local frame using the region origin.
"""

import math
from dataclasses import dataclass

from ezdxf.entities.arc import Arc
from ezdxf.entities.insert import Insert
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.layouts.layout import Modelspace
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.models.geometry import (
    Door,
    DoorSwing,
    Fixture,
    Furniture,
    Point,
    Room,
    RoomType,
    Window,
)
from lighting_engine.parser.door_detection import collect_door_positions
from lighting_engine.parser.geometry import PlanRegion
from lighting_engine.parser.layers import LayerRole
from lighting_engine.parser.snap import (
    _overlap_fraction,  # pyright: ignore[reportPrivateUsage]
    _perp_distance_point_to_line,  # pyright: ignore[reportPrivateUsage]
    _WallLine,  # pyright: ignore[reportPrivateUsage]
)
from lighting_engine.parser.window_filter import filter_valid_windows

# --- Window edge-routing thresholds ---------------------------------------
# Match the values used by `filter_valid_windows` so a cluster that passes
# the filter is always assignable to at least one room edge.
_WINDOW_EDGE_MAX_PERP_DIST_M = 0.4
_WINDOW_EDGE_MAX_PARALLEL_DEG = 15.0
_WINDOW_EDGE_MIN_OVERLAP_FRAC = 0.5

# Room names treated as outdoors regardless of RoomType. Mirrors the hints
# used by `parser/window_filter._is_interior_room`. Kept in sync manually —
# this routing pass needs the same interior/exterior split as the upstream
# filter so we don't route a window onto a TERRACE or BALCONY polygon edge.
_OUTDOOR_NAME_HINTS: tuple[str, ...] = ("terrace", "balcony")

# Distance threshold (meters) for grouping window line-segment endpoints into a
# single window cluster. Tuned to typical mullion/frame spacing.
_WINDOW_CLUSTER_GAP_M = 1.0


@dataclass
class AttachSummary:
    walls_seen: int = 0
    windows_attached: int = 0
    doors_attached: int = 0
    furniture_attached: int = 0
    fixtures_attached: int = 0
    skipped_outside_region: int = 0
    # Window-filter accounting: how many raw window LINE segments we saw on
    # window/GLASS layers vs. how many survived the "must sit on an interior
    # room wall" filter. The dropped count is parapet/terrace/courtyard
    # boundary linework that lives on the window layer but isn't a window.
    window_segments_seen: int = 0
    window_segments_kept: int = 0
    window_segments_dropped: int = 0
    # Doors that were detected but dropped because their position is too far
    # from any room polygon edge — wardrobe doors, shower detail arcs, and
    # other interior linework on the door layer that isn't a real door.
    doors_dropped_interior: int = 0


# A door's centroid is its chord midpoint, which sits ON the wall the door
# is mounted in. Anything more than this from a polygon edge is interior
# linework (wardrobe leaf, shower detail, cabinet) and should be dropped.
_DOOR_EDGE_PROXIMITY_M = 0.4


def _distance_to_polygon_edge(
    point: tuple[float, float], polygon: list[Point],
) -> float:
    """Min perpendicular distance from `point` to any edge of `polygon`."""
    px, py = point
    best = math.inf
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        dx = b.x - a.x
        dy = b.y - a.y
        l2 = dx * dx + dy * dy
        if l2 == 0:
            continue
        t = max(0.0, min(1.0, ((px - a.x) * dx + (py - a.y) * dy) / l2))
        fx = a.x + t * dx
        fy = a.y + t * dy
        d = math.hypot(fx - px, fy - py)
        if d < best:
            best = d
    return best


def _room_centroid(room: Room) -> tuple[float, float]:
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _room_shapely_polygons(rooms: list[Room]) -> list[ShapelyPolygon]:
    return [ShapelyPolygon([(p.x, p.y) for p in r.polygon]) for r in rooms]


def attach_room_index(
    rooms: list[Room],
    room_polys: list[ShapelyPolygon],
    point: tuple[float, float],
) -> int:
    """Return the index of the Room that owns this point.

    Primary: shapely point-in-polygon. Fallback: nearest centroid (for points
    that legitimately sit outside every room — e.g. balcony fixtures on the
    outside of a wall).
    """
    p = ShapelyPoint(point)
    for i, poly in enumerate(room_polys):
        if poly.contains(p) or poly.boundary.distance(p) < 0.05:
            return i
    return nearest_room_index(rooms, point)


def nearest_room_index(rooms: list[Room], point: tuple[float, float]) -> int:
    """Fallback used by attach_room_index when no polygon contains the point."""
    px, py = point
    best_i = 0
    best_d = math.inf
    for i, r in enumerate(rooms):
        cx, cy = _room_centroid(r)
        d = (cx - px) ** 2 + (cy - py) ** 2
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def _to_local_m(
    x_in: float, y_in: float, region: PlanRegion, scale: float
) -> tuple[float, float]:
    return (x_in - region.min_x) * scale, (y_in - region.min_y) * scale


def _snap_to_nearest_wall(
    room: Room, point: tuple[float, float],
) -> tuple[int, float]:
    """Return (wall_index, along_wall_fraction) for the nearest polygon edge.

    `wall_index` is the index of the polygon vertex where the edge starts.
    `along_wall` is the 0–1 fraction along that edge of the foot of the
    perpendicular from `point`. Used to position doors/windows on a specific
    wall of a room.
    """
    px, py = point
    poly = room.polygon
    best_i = 0
    best_d = math.inf
    best_t = 0.5
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        dx = b.x - a.x
        dy = b.y - a.y
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            continue
        t = ((px - a.x) * dx + (py - a.y) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        foot_x = a.x + t * dx
        foot_y = a.y + t * dy
        d = (foot_x - px) ** 2 + (foot_y - py) ** 2
        if d < best_d:
            best_d = d
            best_i = i
            best_t = t
    return best_i, best_t


def _seg_min_endpoint_dist_sq(
    s1: tuple[tuple[float, float], tuple[float, float]],
    s2: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    """Minimum squared distance between any endpoint of s1 and any endpoint of s2."""
    best = math.inf
    for ax, ay in s1:
        for bx, by in s2:
            d = (ax - bx) ** 2 + (ay - by) ** 2
            if d < best:
                best = d
    return best


def cluster_window_lines(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    max_gap_m: float = _WINDOW_CLUSTER_GAP_M,
) -> list[list[tuple[tuple[float, float], tuple[float, float]]]]:
    """Group line segments into clusters where any two segments share an endpoint
    or have endpoints within max_gap_m.  Union-find on endpoint proximity gives
    correct transitive grouping for window mullion chains."""
    if not segments:
        return []
    parent = list(range(len(segments)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    threshold_sq = max_gap_m * max_gap_m
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            if _seg_min_endpoint_dist_sq(segments[i], segments[j]) <= threshold_sq:
                union(i, j)

    groups: dict[int, list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    for idx, seg in enumerate(segments):
        root = find(idx)
        groups.setdefault(root, []).append(seg)
    return list(groups.values())


def _is_interior_room_for_windows(room: Room) -> bool:
    """Mirror of `parser/window_filter._is_interior_room` for cluster routing.

    A window cluster only makes sense on an interior room's wall — we exclude
    `RoomType.outdoor`, `RoomType.staircase`, and rooms whose name hints at a
    terrace or balcony. Kept here (rather than imported) because the upstream
    helper is module-private and pyright-strict makes the cross-module reuse
    noisy enough to inline.
    """
    if room.type in (RoomType.outdoor, RoomType.staircase):
        return False
    lower = room.name.lower()
    return not any(hint in lower for hint in _OUTDOOR_NAME_HINTS)


def _cluster_principal_segment(
    cluster: list[tuple[tuple[float, float], tuple[float, float]]],
) -> tuple[Point, Point]:
    """Approximate the cluster by a single segment along its principal axis.

    For routing we treat the cluster as one conceptual window. We compute the
    centroid, decide the cluster's long axis (horizontal vs vertical based on
    bounding-box extents), and emit a segment along that axis that spans the
    cluster's bbox extent in the chosen direction. This is what we feed to
    `_find_best_wall` so the parallel / overlap / perpendicular checks the
    snap module already implements work uniformly.
    """
    xs = [p[0] for seg in cluster for p in seg]
    ys = [p[1] for seg in cluster for p in seg]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    width = maxx - minx
    height = maxy - miny
    if width >= height:
        return Point(x=minx, y=cy), Point(x=maxx, y=cy)
    return Point(x=cx, y=miny), Point(x=cx, y=maxy)


def _room_edge_walls(room: Room) -> list[_WallLine]:
    """Build a `_WallLine` for each polygon edge of `room`."""
    out: list[_WallLine] = []
    polygon = room.polygon
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        length = math.hypot(b.x - a.x, b.y - a.y)
        if length <= 0.0:
            continue
        out.append(_WallLine(
            p1=(a.x, a.y),
            p2=(b.x, b.y),
            dx=(b.x - a.x) / length,
            dy=(b.y - a.y) / length,
            length=length,
        ))
    return out


def _route_cluster_by_edge(
    cluster: list[tuple[tuple[float, float], tuple[float, float]]],
    rooms: list[Room],
    room_edge_walls: list[list[_WallLine]],
) -> tuple[int, int, tuple[float, float]] | None:
    """Pick the (room, wall_index) whose polygon edge best matches `cluster`.

    Returns `(room_index, wall_index, snap_point)` where `snap_point` is the
    midpoint of the cluster's principal segment in local meters. Returns None
    when no interior room has a qualifying edge — caller falls back to the
    point-in-polygon route.

    Selection score (higher = better) is a tuple `(coverage_tier, -perp)`:
      • `coverage_tier` = 1 when the room's edge fully covers the cluster
        (overlap fraction ≥ 0.999), else 0. A window cannot extend past its
        host wall, so a fully-covering edge is architecturally correct and
        beats a partially-covering edge of a neighbouring room. This fixes
        the case where a wide bedroom window has both the bedroom's long
        south wall (full cover) and the adjacent toilet's shorter north
        wall (partial cover) within the perp tolerance — we pick the
        bedroom.
      • `-perp` (negative perp distance) breaks ties within a tier — closer
        edge wins.

    All candidate edges must pass the same parallel / overlap / perp
    thresholds as `filter_valid_windows`, so a cluster that survived the
    filter is guaranteed at least one passing candidate here.
    """
    a, b = _cluster_principal_segment(cluster)
    snap_point = ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
    cluster_len = math.hypot(b.x - a.x, b.y - a.y)
    if cluster_len <= 0.0:
        return None
    edge_dx_unit = (b.x - a.x) / cluster_len
    edge_dy_unit = (b.y - a.y) / cluster_len

    best_room_idx: int | None = None
    best_wall_idx: int | None = None
    # Score tuple: (full_coverage_flag, -perp_distance). Higher is better.
    best_score: tuple[int, float] = (-1, -math.inf)

    for ri, room in enumerate(rooms):
        if not _is_interior_room_for_windows(room):
            continue
        walls = room_edge_walls[ri]
        if not walls:
            continue
        # Find ALL qualifying edges (passing parallel + overlap + perp). We
        # need to consider every edge so a long bedroom wall can outrank a
        # shorter neighbour wall even when the neighbour is geometrically
        # closer.
        for wi, wall in enumerate(walls):
            # Same checks as `_find_best_wall`, applied per-edge so we can
            # score every qualifying edge rather than only the closest.
            cos = abs(edge_dx_unit * wall.dx + edge_dy_unit * wall.dy)
            cos = max(-1.0, min(1.0, cos))
            angle_deg = math.degrees(math.acos(cos))
            if angle_deg > _WINDOW_EDGE_MAX_PARALLEL_DEG:
                continue
            mx, my = snap_point
            perp = _perp_distance_point_to_line(mx, my, wall)
            if perp > _WINDOW_EDGE_MAX_PERP_DIST_M:
                continue
            overlap = _overlap_fraction(a.x, a.y, b.x, b.y, wall)
            if overlap < _WINDOW_EDGE_MIN_OVERLAP_FRAC:
                continue
            full_cover = 1 if overlap >= 0.999 else 0
            score = (full_cover, -perp)
            if score > best_score:
                best_score = score
                best_room_idx = ri
                # Map back from wall_lines list index to polygon vertex
                # index. _room_edge_walls preserves polygon vertex order
                # except it skips zero-length edges, so we re-walk the
                # polygon and count emitted edges to find the right index.
                best_wall_idx = _polygon_wall_index_for_emitted(
                    room.polygon, wi,
                )
    if best_room_idx is None or best_wall_idx is None:
        return None
    return best_room_idx, best_wall_idx, snap_point


def _polygon_wall_index_for_emitted(
    polygon: list[Point], emitted_index: int,
) -> int:
    """Map an emitted-edge index (from `_room_edge_walls`) back to a polygon
    vertex index. Zero-length edges are skipped during emission, so we walk
    the polygon and count non-degenerate edges until we hit `emitted_index`.
    """
    count = 0
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        if math.hypot(b.x - a.x, b.y - a.y) <= 0.0:
            continue
        if count == emitted_index:
            return i
        count += 1
    return 0


def _window_from_cluster(
    cluster: list[tuple[tuple[float, float], tuple[float, float]]],
    *,
    window_id: str,
    is_glazed_door: bool,
) -> Window:
    xs = [p[0] for seg in cluster for p in seg]
    ys = [p[1] for seg in cluster for p in seg]
    width_m = max(xs) - min(xs)
    height_m = max(ys) - min(ys)
    long_side = max(width_m, height_m)
    return Window(
        id=window_id,
        width_m=max(long_side, 0.3),
        height_m=1.2,           # default residential window height; refined later
        sill_height_m=0.9,
        is_glazed_door=is_glazed_door,
    )


def attach_entities(
    msp: Modelspace,
    rooms: list[Room],
    layer_roles: dict[LayerRole, list[str]],
    *,
    region: PlanRegion,
    dxf_unit_to_m: float = 0.0254,
) -> AttachSummary:
    """Walk modelspace; attach entities to their containing room. Mutates `rooms`."""
    summary = AttachSummary()
    if not rooms:
        return summary

    # Pre-compute shapely polygons once for point-in-polygon attachment
    room_polys = _room_shapely_polygons(rooms)

    wall_layers = set(layer_roles.get(LayerRole.wall, []))
    window_layers = set(layer_roles.get(LayerRole.window, []))
    door_layers = set(layer_roles.get(LayerRole.door, []))
    furniture_layers = set(layer_roles.get(LayerRole.furniture, []))
    fixture_layers = set(layer_roles.get(LayerRole.fixture, []))

    # ----- DOORS (INSERT / ARC / LINE-pair / LWPOLYLINE-pair on door layers) -----
    # See parser/door_detection.py — the architect can draw a door as any of
    # those four primitives. The collector returns a flat list of `DoorRaw`
    # records already converted to local meters; we then attach each one to
    # the room whose polygon contains it (or whose centroid is closest as a
    # fallback) and snap to that room's nearest wall.
    raw_doors = collect_door_positions(
        msp, door_layers, region, dxf_unit_to_m,
    )
    for raw in raw_doors:
        idx = attach_room_index(rooms, room_polys, raw.position)
        room = rooms[idx]
        # Door-edge filter: real doors sit ON the wall they open through.
        # Anything more than ~0.4m from any polygon edge is interior linework
        # (wardrobe leaf, shower detail, cabinet) and should be dropped.
        # This is the same principle filter_valid_windows applies to window
        # glyphs.
        if _distance_to_polygon_edge(raw.position, room.polygon) > _DOOR_EDGE_PROXIMITY_M:
            summary.doors_dropped_interior += 1
            continue
        wall_idx, along = _snap_to_nearest_wall(room, raw.position)
        # Width: prefer the arc-derived value (chord = 2 * r * sin(sweep/2),
        # approximated as r * sqrt(2) for the common 90° swing). Fall back
        # to a residential default when unknown.
        if raw.swing_radius_m is not None:
            width_m = max(raw.swing_radius_m * math.sqrt(2.0), 0.3)
        else:
            width_m = 0.9
        door = Door(
            id=f"door-{summary.doors_attached:03d}",
            wall_index=wall_idx,
            along_wall=along,
            width_m=width_m,
            swing=DoorSwing.unknown,
        )
        room.doors.append(door)
        summary.doors_attached += 1

    # ----- WINDOWS (clustered segments on window/glass layers) -----
    # Architects draw window glyphs as three different entity types: LINE
    # pairs (straight glazing), LWPOLYLINE rectangles (closed frames), and
    # ARC entities (casement-window swing symbols). _wall_segments and the
    # visualizer already handle LINE + LWPOLYLINE; this pass must collect
    # ALL THREE or rooms whose windows are drawn as polylines/arcs (DINING,
    # KITCHEN, DRAWING ROOM in the Delhi fixture) end up with zero attached
    # windows in the IR despite the SVG showing window glyphs. After
    # collection, filter_valid_windows() drops anything not on an interior
    # room's wall (parapets / terraces / etc.).
    raw_win_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    raw_win_glazed_flag: list[bool] = []

    def _append_segment(
        x1: float, y1: float, x2: float, y2: float, layer_name: str,
    ) -> None:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if not region.contains((mx, my)):
            summary.skipped_outside_region += 1
            return
        a = _to_local_m(x1, y1, region, dxf_unit_to_m)
        b = _to_local_m(x2, y2, region, dxf_unit_to_m)
        raw_win_segments.append((a, b))
        raw_win_glazed_flag.append("glass" in layer_name.lower())

    for e in msp.query("LINE"):
        if e.dxf.layer not in window_layers:
            continue
        _append_segment(
            float(e.dxf.start.x), float(e.dxf.start.y),
            float(e.dxf.end.x), float(e.dxf.end.y),
            e.dxf.layer,
        )

    for e in msp.query("LWPOLYLINE"):
        if not isinstance(e, LWPolyline):
            continue
        if e.dxf.layer not in window_layers:
            continue
        verts = [(float(v[0]), float(v[1])) for v in e.get_points()]
        for i in range(len(verts) - 1):
            _append_segment(
                verts[i][0], verts[i][1],
                verts[i + 1][0], verts[i + 1][1],
                e.dxf.layer,
            )
        if e.closed and len(verts) >= 3:
            _append_segment(
                verts[-1][0], verts[-1][1],
                verts[0][0], verts[0][1],
                e.dxf.layer,
            )

    # ARC = casement-window swing symbol. The chord (start point → end point)
    # approximates the glass plane the swing rests on, which is what we
    # want for window placement.
    for e in msp.query("ARC"):
        if not isinstance(e, Arc):
            continue
        if e.dxf.layer not in window_layers:
            continue
        start_pt = e.start_point
        end_pt = e.end_point
        _append_segment(
            float(start_pt.x), float(start_pt.y),
            float(end_pt.x), float(end_pt.y),
            e.dxf.layer,
        )

    summary.window_segments_seen = len(raw_win_segments)
    kept_segments, dropped_segments = filter_valid_windows(
        raw_win_segments, rooms,
    )
    summary.window_segments_kept = len(kept_segments)
    summary.window_segments_dropped = len(dropped_segments)

    # Carry the glazed-flag through the filter. `kept_segments` preserves
    # input order, so we walk the raw list in lock-step with a pointer into
    # the kept list and pick out the matching glazed flags.
    win_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    win_glazed_flag: list[bool] = []
    kept_idx = 0
    for seg, glazed in zip(raw_win_segments, raw_win_glazed_flag, strict=True):
        if kept_idx < len(kept_segments) and seg == kept_segments[kept_idx]:
            win_segments.append(seg)
            win_glazed_flag.append(glazed)
            kept_idx += 1

    clusters = cluster_window_lines(win_segments, max_gap_m=_WINDOW_CLUSTER_GAP_M)
    # Pre-compute each room's polygon edges once for edge-best-match routing.
    # Architects draw window glyphs straddling the wall, so the cluster's
    # midpoint sits on the OUTSIDE face of the wall — point-in-polygon
    # routes the window to whichever neighbour's polygon happens to contain
    # that exterior point (often a courtyard, the room on the wrong side of
    # the wall, or a passage). Edge-best-match instead picks the interior
    # room whose polygon edge is closest to (and parallel to / overlapping)
    # the cluster, which is the room the architect actually drew the
    # window for. Same parallel / overlap / perp thresholds as
    # `filter_valid_windows`.
    room_edge_walls: list[list[_WallLine]] = [
        _room_edge_walls(r) for r in rooms
    ]
    for ci, cluster in enumerate(clusters):
        mid_x = sum(((s[0][0] + s[1][0]) / 2) for s in cluster) / len(cluster)
        mid_y = sum(((s[0][1] + s[1][1]) / 2) for s in cluster) / len(cluster)
        cluster_indices = [i for i, seg in enumerate(win_segments) if seg in cluster]
        glazed = (
            sum(win_glazed_flag[i] for i in cluster_indices) > len(cluster_indices) / 2
        )
        window = _window_from_cluster(
            cluster, window_id=f"win-{ci:03d}", is_glazed_door=glazed,
        )
        routing = _route_cluster_by_edge(cluster, rooms, room_edge_walls)
        if routing is not None:
            idx, wall_idx, snap_point = routing
            _, along = _snap_to_nearest_wall(rooms[idx], snap_point)
        else:
            # Fallback: midpoint-based attach when no interior room's polygon
            # edge qualifies (e.g. the cluster sits in a region between rooms
            # where no polygon was extracted). Preserves prior behaviour for
            # clusters the new router can't place.
            idx = attach_room_index(rooms, room_polys, (mid_x, mid_y))
            wall_idx, along = _snap_to_nearest_wall(rooms[idx], (mid_x, mid_y))
        window = window.model_copy(update={"wall_index": wall_idx, "along_wall": along})
        rooms[idx].windows.append(window)
        summary.windows_attached += 1

    # ----- FURNITURE (INSERTs on furniture layers) -----
    for e in msp.query("INSERT"):
        if not isinstance(e, Insert) or e.dxf.layer not in furniture_layers:
            continue
        x, y = float(e.dxf.insert.x), float(e.dxf.insert.y)
        if not region.contains((x, y)):
            summary.skipped_outside_region += 1
            continue
        lx, ly = _to_local_m(x, y, region, dxf_unit_to_m)
        idx = attach_room_index(rooms, room_polys, (lx, ly))
        rooms[idx].furniture.append(Furniture(
            id=f"furn-{summary.furniture_attached:03d}",
            raw_label=e.dxf.name,
            type="unknown",
            position=Point(x=lx, y=ly),
        ))
        summary.furniture_attached += 1

    # ----- FIXTURES (INSERTs on fixture layers) -----
    for e in msp.query("INSERT"):
        if not isinstance(e, Insert) or e.dxf.layer not in fixture_layers:
            continue
        x, y = float(e.dxf.insert.x), float(e.dxf.insert.y)
        if not region.contains((x, y)):
            summary.skipped_outside_region += 1
            continue
        lx, ly = _to_local_m(x, y, region, dxf_unit_to_m)
        idx = attach_room_index(rooms, room_polys, (lx, ly))
        rooms[idx].existing_fixtures.append(Fixture(
            id=f"fix-{summary.fixtures_attached:03d}",
            raw_label=e.dxf.name,
            position=Point(x=lx, y=ly),
        ))
        summary.fixtures_attached += 1

    # Count walls only for the summary (no attachment in v1)
    summary.walls_seen = sum(
        1 for _ in msp.query("LINE") if _.dxf.layer in wall_layers
    )

    return summary
