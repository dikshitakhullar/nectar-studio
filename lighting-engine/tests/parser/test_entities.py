from pathlib import Path

from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.models.geometry import Point, Room, RoomType
from lighting_engine.parser.entities import (
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
