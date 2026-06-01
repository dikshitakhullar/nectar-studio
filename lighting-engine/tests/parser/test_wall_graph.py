from pathlib import Path

from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.wall_graph import (
    extract_room_faces,
    innermost_face_containing,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


def _square_segments(x0: float, y0: float, side: float) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [
        ((x0, y0), (x0 + side, y0)),
        ((x0 + side, y0), (x0 + side, y0 + side)),
        ((x0 + side, y0 + side), (x0, y0 + side)),
        ((x0, y0 + side), (x0, y0)),
    ]


def test_four_lines_forming_square_yields_one_face():
    faces = extract_room_faces(_square_segments(0, 0, 120), min_area=100.0)
    assert len(faces) == 1
    assert faces[0].area == 120 * 120


def test_two_adjacent_squares_sharing_a_wall_yield_two_faces():
    # Left square 0..120 and right square 120..240, sharing the x=120 wall
    segs = _square_segments(0, 0, 120) + _square_segments(120, 0, 120)
    faces = extract_room_faces(segs, min_area=100.0)
    assert len(faces) == 2


def test_endpoints_off_by_less_than_tolerance_still_close():
    # Make a "square" where endpoints don't quite match (off by 0.5 in)
    segs = [
        ((0.0, 0.0),   (120.0, 0.0)),
        ((120.5, 0.0), (120.0, 120.0)),    # x off by 0.5
        ((120.0, 120.5), (0.0, 120.0)),    # y off by 0.5
        ((0.0, 120.0), (0.0, 0.5)),        # y off by 0.5
    ]
    faces = extract_room_faces(segs, snap_tolerance=1.0, min_area=100.0)
    assert len(faces) == 1


def test_disconnected_lines_yield_no_faces():
    segs = [
        ((0.0, 0.0), (10.0, 0.0)),
        ((50.0, 50.0), (60.0, 50.0)),
    ]
    assert extract_room_faces(segs, min_area=10.0) == []


def test_innermost_face_picks_smallest_containing_face():
    # An outer square (200) and an inner square (100) sharing a center; a point
    # inside the inner square is contained by BOTH faces, but innermost wins.
    outer = _square_segments(0, 0, 200)
    inner = _square_segments(50, 50, 100)
    faces = extract_room_faces(outer + inner, min_area=10.0)
    # 3 candidate faces: outer (40000), inner (10000), and the ring between them (30000)
    assert len(faces) >= 2
    inside_inner = innermost_face_containing(faces, (100.0, 100.0))
    assert inside_inner is not None
    assert inside_inner.area == 100 * 100


def test_polygonize_on_real_walls_yields_at_least_some_closed_faces():
    """Sanity check that polygonize runs on real-world wall geometry without
    crashing and produces *some* output.

    NOTE: This does NOT validate that the faces correspond to actual rooms.
    Real Delhi DWGs have walls drawn as loose line segments broken by doors,
    so polygonize doesn't reliably find room-sized closed loops. Production
    room extraction in `rooms.py` uses a ray-cast approach instead. This test
    documents that wall_graph is plumbed to real fixtures correctly.
    """
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    msp = rep.document.modelspace()
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for e in msp.query("LINE"):
        if e.dxf.layer != "WALL":
            continue
        segments.append((
            (float(e.dxf.start.x), float(e.dxf.start.y)),
            (float(e.dxf.end.x), float(e.dxf.end.y)),
        ))
    # Loose params so polygonize finds anything closed at all
    faces = extract_room_faces(
        segments, snap_tolerance=1.0, min_area=100.0, max_aspect_ratio=20.0
    )
    assert len(faces) >= 1, f"no closed faces at all from {len(segments)} walls"


def test_aspect_ratio_filter_drops_wall_sliver_shaped_faces():
    # A 4m × 100mm sliver = 400 × 10 cm; in inches that's roughly 157.5 × 3.94.
    # Build a closed thin rectangle and confirm it's filtered out.
    segs = [
        ((0.0, 0.0),  (157.5, 0.0)),
        ((157.5, 0.0), (157.5, 3.94)),
        ((157.5, 3.94), (0.0, 3.94)),
        ((0.0, 3.94), (0.0, 0.0)),
    ]
    # Area ~= 620 sq-in, which beats the OLD 144 floor but should be dropped by aspect filter.
    faces = extract_room_faces(segs, min_area=100.0, max_aspect_ratio=5.0)
    assert faces == []
    # With aspect filter relaxed, the same input gives one face
    faces2 = extract_room_faces(segs, min_area=100.0, max_aspect_ratio=100.0)
    assert len(faces2) == 1
