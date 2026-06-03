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
    Window,
)
from lighting_engine.parser.door_detection import collect_door_positions
from lighting_engine.parser.geometry import PlanRegion
from lighting_engine.parser.layers import LayerRole
from lighting_engine.parser.window_filter import filter_valid_windows

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
    for ci, cluster in enumerate(clusters):
        mid_x = sum(((s[0][0] + s[1][0]) / 2) for s in cluster) / len(cluster)
        mid_y = sum(((s[0][1] + s[1][1]) / 2) for s in cluster) / len(cluster)
        idx = attach_room_index(rooms, room_polys, (mid_x, mid_y))
        cluster_indices = [i for i, seg in enumerate(win_segments) if seg in cluster]
        glazed = (
            sum(win_glazed_flag[i] for i in cluster_indices) > len(cluster_indices) / 2
        )
        window = _window_from_cluster(
            cluster, window_id=f"win-{ci:03d}", is_glazed_door=glazed,
        )
        # Snap the window to a specific wall of its room
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
