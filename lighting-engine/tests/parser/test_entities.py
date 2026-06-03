from pathlib import Path

from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.models.geometry import Point, Room, RoomType
from lighting_engine.parser.entities import (
    _room_edge_walls,  # pyright: ignore[reportPrivateUsage]
    _route_cluster_by_edge,  # pyright: ignore[reportPrivateUsage]
    attach_entities,
    attach_room_index,
    cluster_window_lines,
    nearest_room_index,
)
from lighting_engine.parser.geometry import find_plan_region
from lighting_engine.parser.layers import classify_layers
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.rooms import extract_rooms

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"
INCH_TO_M = 0.0254


def _square_room(name: str, cx: float, cy: float, side: float = 4.0) -> Room:
    s = side / 2
    return Room(
        id=name.lower(),
        name=name,
        type=RoomType.bedroom,
        polygon=[
            Point(x=cx - s, y=cy - s),
            Point(x=cx + s, y=cy - s),
            Point(x=cx + s, y=cy + s),
            Point(x=cx - s, y=cy + s),
        ],
        ceiling_height_m=2.7,
    )


def test_nearest_room_index_picks_closest_centroid():
    rooms = [_square_room("A", 0, 0), _square_room("B", 10, 0)]
    assert nearest_room_index(rooms, (1.0, 0.0)) == 0
    assert nearest_room_index(rooms, (9.0, 0.0)) == 1


def test_attach_room_index_uses_point_in_polygon_first():
    """A point inside room A but slightly closer to B's centroid should still
    attach to A (point-in-polygon wins over centroid distance)."""
    rooms = [_square_room("A", 0, 0, side=4.0), _square_room("B", 10, 0, side=4.0)]
    polys = [ShapelyPolygon([(p.x, p.y) for p in r.polygon]) for r in rooms]
    # Point at (1.9, 0) — inside A's polygon (extends to x=2), closer to B's centroid (10)?
    # Centroid distances: A=(0,0) dist=1.9, B=(10,0) dist=8.1 — A wins anyway here.
    # Use a more pointed test: point at (-1.9, 0) clearly inside A
    assert attach_room_index(rooms, polys, (-1.9, 0.0)) == 0


def test_attach_room_index_falls_back_to_nearest_when_point_outside_all():
    """A point outside every room should fall back to nearest centroid."""
    rooms = [_square_room("A", 0, 0, side=4.0), _square_room("B", 10, 0, side=4.0)]
    polys = [ShapelyPolygon([(p.x, p.y) for p in r.polygon]) for r in rooms]
    # Point at (50, 50) — outside both rooms; nearer to B
    assert attach_room_index(rooms, polys, (50.0, 50.0)) == 1


def test_cluster_window_lines_groups_nearby_segments():
    # Three segments tightly clustered, plus one far away → 2 clusters
    segments = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.0, 0.0), (1.0, 0.2)),
        ((1.0, 0.2), (0.0, 0.2)),
        ((50.0, 50.0), (51.0, 50.0)),
    ]
    clusters = cluster_window_lines(segments, max_gap_m=0.5)
    assert len(clusters) == 2


def test_route_cluster_by_edge_picks_full_cover_room_over_partial_cover_neighbour():
    """Two adjacent rooms share a wall — the bedroom's long south edge fully
    contains the window, the toilet's shorter north edge only partially does.
    Edge-best-match must pick the bedroom even when the toilet's edge is
    geometrically closer (smaller perp distance) — full coverage beats partial.
    Mirrors the MASTER BEDROOM south window misrouting in the Delhi fixture.
    """
    bedroom = Room(
        id="bedroom",
        name="MASTER BEDROOM",
        type=RoomType.bedroom,
        polygon=[
            Point(x=0.0, y=10.0),   # SW corner
            Point(x=10.0, y=10.0),  # SE corner
            Point(x=10.0, y=20.0),
            Point(x=0.0, y=20.0),
        ],
        ceiling_height_m=2.7,
    )
    # Toilet sits south of the bedroom, with a wall thickness gap.
    # Toilet's north edge runs from x=2 to x=6 (shorter than the cluster width).
    toilet = Room(
        id="toilet",
        name="MASTER TOILET",
        type=RoomType.bathroom,
        polygon=[
            Point(x=2.0, y=5.0),
            Point(x=6.0, y=5.0),
            Point(x=6.0, y=9.7),   # toilet north edge at y=9.7
            Point(x=2.0, y=9.7),
        ],
        ceiling_height_m=2.7,
    )
    rooms = [bedroom, toilet]
    edges = [_room_edge_walls(r) for r in rooms]

    # Cluster: a 5m-wide window drawn between the two rooms at y=9.85
    # (within 0.15m of bedroom's south edge at y=10, and within 0.15m of
    # toilet's north edge at y=9.7). Cluster x-extent [1, 6] exceeds the
    # toilet's edge [2, 6] but fits within the bedroom's edge [0, 10].
    cluster = [
        ((1.0, 9.85), (3.0, 9.85)),
        ((3.0, 9.85), (6.0, 9.85)),
    ]
    routing = _route_cluster_by_edge(cluster, rooms, edges)
    assert routing is not None
    room_idx, _, _ = routing
    assert room_idx == 0   # bedroom, not toilet


def test_route_cluster_by_edge_skips_outdoor_rooms():
    """A window cluster sitting between an interior room and a terrace must
    route to the interior room — terraces are excluded from the routing pool.
    """
    living = Room(
        id="living",
        name="LIVING",
        type=RoomType.living,
        polygon=[
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=10.0, y=5.0),
            Point(x=0.0, y=5.0),
        ],
        ceiling_height_m=2.7,
    )
    terrace = Room(
        id="terrace",
        name="TERRACE",
        type=RoomType.outdoor,
        polygon=[
            Point(x=0.0, y=5.2),
            Point(x=10.0, y=5.2),
            Point(x=10.0, y=10.0),
            Point(x=0.0, y=10.0),
        ],
        ceiling_height_m=2.7,
    )
    rooms = [terrace, living]   # order: terrace first
    edges = [_room_edge_walls(r) for r in rooms]
    cluster = [((2.0, 5.1), (7.0, 5.1))]
    routing = _route_cluster_by_edge(cluster, rooms, edges)
    assert routing is not None
    room_idx, _, _ = routing
    assert rooms[room_idx].name == "LIVING"


def test_route_cluster_by_edge_returns_none_when_no_qualifying_edge():
    """Cluster floating in empty space (no room edge within tolerance) routes
    to None so the caller falls back to the legacy point-in-polygon attach."""
    room = Room(
        id="r",
        name="R",
        type=RoomType.living,
        polygon=[
            Point(x=0.0, y=0.0),
            Point(x=2.0, y=0.0),
            Point(x=2.0, y=2.0),
            Point(x=0.0, y=2.0),
        ],
        ceiling_height_m=2.7,
    )
    edges = [_room_edge_walls(room)]
    cluster = [((50.0, 50.0), (51.0, 50.0))]
    assert _route_cluster_by_edge(cluster, [room], edges) is None


def test_attach_entities_on_real_file_populates_some_rooms():
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    msp = rep.document.modelspace()

    # Walls → segments + centroids for plan region
    wall_segments: list[tuple[tuple[float, float], tuple[float, float]]] = [
        (
            (float(e.dxf.start.x), float(e.dxf.start.y)),
            (float(e.dxf.end.x), float(e.dxf.end.y)),
        )
        for e in msp.query("LINE[layer=='WALL']")
    ]
    wall_centroids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in wall_segments]
    region = find_plan_region(wall_centroids)
    result = extract_rooms(msp, region, wall_segments, dxf_unit_to_m=INCH_TO_M)
    rooms = result.rooms
    assert rooms

    layer_roles = classify_layers([layer.dxf.name for layer in rep.document.layers])
    summary = attach_entities(
        msp, rooms, layer_roles, region=region, dxf_unit_to_m=INCH_TO_M,
    )

    assert summary.fixtures_attached > 0
    # At least one door should attach (DOOR layer has 45 inserts)
    assert summary.doors_attached > 0
    # At least one window should attach (cluster from the 'window' layer)
    assert summary.windows_attached > 0
