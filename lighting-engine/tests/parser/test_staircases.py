from pathlib import Path

import ezdxf as _ezdxf

from lighting_engine.models.geometry import RoomType
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.pipeline import parse_file
from lighting_engine.parser.staircases import (
    cluster_staircase_labels,
    detect_staircase_anchors,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


def _add_parallel_steps_lines(
    msp: "_ezdxf.layouts.Modelspace",
    cx: float,
    cy: float,
    n_treads: int = 8,
    tread_depth: float = 10.0,
    tread_width: float = 40.0,
) -> None:
    """Add n_treads horizontal LINE entities on the STEPS layer centred at (cx, cy).

    Each tread is a horizontal line at a different y-offset.  The resulting
    bbox is [cx - tread_width/2 .. cx + tread_width/2] × [cy - … .. cy + …].
    """
    half_height = (n_treads - 1) * tread_depth / 2.0
    half_width = tread_width / 2.0
    for i in range(n_treads):
        y = cy - half_height + i * tread_depth
        msp.add_line(
            start=(cx - half_width, y),
            end=(cx + half_width, y),
            dxfattribs={"layer": "STEPS"},
        )


def test_detect_up_and_dn_labels(tmp_path: Path) -> None:
    doc = _ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()
    msp.add_mtext(r"\A1;\pxqc;UP", dxfattribs={"layer": "TEXT"}).set_location((100.0, 100.0))
    msp.add_mtext(r"\A1;\pxqc;DN", dxfattribs={"layer": "TEXT"}).set_location((100.0, 200.0))
    dxf_path = tmp_path / "synth_stair.dxf"
    doc.saveas(str(dxf_path))

    rep = load_drawing(dxf_path)
    anchors = detect_staircase_anchors(rep.document.modelspace())
    # UP and DN within cluster distance → one staircase
    assert len(anchors) == 1
    a = anchors[0]
    assert a.has_up
    assert a.has_dn
    # No STEPS layer in this DXF → label centroid, no tread bbox
    assert a.tread_bbox_in is None
    # Centroid roughly between the two labels
    assert abs(a.x - 100.0) < 1.0
    assert 100.0 < a.y < 200.0


def test_only_up_label_still_counts_as_staircase(tmp_path: Path) -> None:
    doc = _ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()
    msp.add_mtext(r"\A1;\pxqc;UP", dxfattribs={"layer": "TEXT"}).set_location((50.0, 50.0))
    dxf_path = tmp_path / "synth_stair_up.dxf"
    doc.saveas(str(dxf_path))

    rep = load_drawing(dxf_path)
    anchors = detect_staircase_anchors(rep.document.modelspace())
    assert len(anchors) == 1
    assert anchors[0].has_up
    assert not anchors[0].has_dn


def test_far_apart_labels_form_separate_clusters() -> None:
    # UP labels >300in apart should yield two clusters
    raw_positions = [
        ("UP", 100.0, 100.0),
        ("UP", 600.0, 100.0),  # 500 inches away — different staircase
    ]
    clusters = cluster_staircase_labels(raw_positions, max_distance_in=200.0)
    assert len(clusters) == 2


def test_close_labels_merge_into_one_cluster() -> None:
    raw_positions = [
        ("UP", 100.0, 100.0),
        ("DN", 150.0, 100.0),
        ("UP", 120.0, 150.0),
    ]
    clusters = cluster_staircase_labels(raw_positions, max_distance_in=200.0)
    assert len(clusters) == 1


def test_ignores_text_that_starts_with_up_or_dn_but_is_not_a_marker(tmp_path: Path) -> None:
    doc = _ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()
    # "UPPER FLOOR" should NOT be detected as an UP arrow
    msp.add_mtext(r"\A1;\pxqc;UPPER", dxfattribs={"layer": "TEXT"}).set_location((100.0, 100.0))
    msp.add_mtext(r"\A1;\pxqc;DOOR", dxfattribs={"layer": "TEXT"}).set_location((100.0, 200.0))
    dxf_path = tmp_path / "synth_no_stair.dxf"
    doc.saveas(str(dxf_path))

    rep = load_drawing(dxf_path)
    anchors = detect_staircase_anchors(rep.document.modelspace())
    assert anchors == []


def test_real_delhi_file_detects_at_least_one_staircase() -> None:
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    anchors = detect_staircase_anchors(rep.document.modelspace())
    assert len(anchors) >= 1, (
        "real Delhi file has multiple UP/DN labels — should detect ≥1 staircase"
    )


# ---------------------------------------------------------------------------
# New tests for tread-cluster detection (step 5 of the bug-fix spec)
# ---------------------------------------------------------------------------


def test_tread_cluster_detected_when_steps_lines_present(tmp_path: Path) -> None:
    """Synthetic DXF with UP label AND ≥5 parallel STEPS lines nearby.

    The anchor should have tread_bbox_in set and (x, y) equal to the tread
    cluster centroid (not the label position).
    """
    doc = _ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()

    # UP label at (500, 500)
    label_x, label_y = 500.0, 500.0
    msp.add_mtext(r"\A1;\pxqc;UP", dxfattribs={"layer": "TEXT"}).set_location(
        (label_x, label_y)
    )

    # 8 horizontal STEPS tread lines centred at (500, 350) — ~150 units north of
    # the label, well within the 300-unit search radius.
    tread_cx, tread_cy = 500.0, 350.0
    tread_width = 80.0   # half-width = 40
    n_treads = 8
    tread_depth = 10.0
    half_height = (n_treads - 1) * tread_depth / 2.0  # = 35
    _add_parallel_steps_lines(
        msp, tread_cx, tread_cy, n_treads=n_treads,
        tread_depth=tread_depth, tread_width=tread_width,
    )

    dxf_path = tmp_path / "synth_steps.dxf"
    doc.saveas(str(dxf_path))

    rep = load_drawing(dxf_path)
    anchors = detect_staircase_anchors(rep.document.modelspace())

    assert len(anchors) == 1, f"Expected 1 anchor, got {len(anchors)}"
    a = anchors[0]
    assert a.has_up
    assert not a.has_dn
    assert a.tread_bbox_in is not None, "Expected tread_bbox_in to be set"

    # (x, y) should be the tread centroid, not the label position
    assert abs(a.x - tread_cx) < 1.0, f"Expected x≈{tread_cx}, got {a.x}"
    assert abs(a.y - tread_cy) < 1.0, f"Expected y≈{tread_cy}, got {a.y}"

    # Bbox should wrap the tread lines
    xmin, ymin, xmax, ymax = a.tread_bbox_in
    expected_xmin = tread_cx - tread_width / 2.0
    expected_xmax = tread_cx + tread_width / 2.0
    expected_ymin = tread_cy - half_height
    expected_ymax = tread_cy + half_height
    assert abs(xmin - expected_xmin) < 1.0, f"xmin mismatch: {xmin} vs {expected_xmin}"
    assert abs(xmax - expected_xmax) < 1.0, f"xmax mismatch: {xmax} vs {expected_xmax}"
    assert abs(ymin - expected_ymin) < 1.0, f"ymin mismatch: {ymin} vs {expected_ymin}"
    assert abs(ymax - expected_ymax) < 1.0, f"ymax mismatch: {ymax} vs {expected_ymax}"


def test_no_tread_cluster_when_no_steps_lines(tmp_path: Path) -> None:
    """Synthetic DXF with only a UP label and no STEPS lines.

    The anchor should have tread_bbox_in=None and (x, y) at the label position.
    """
    doc = _ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()

    label_x, label_y = 200.0, 300.0
    msp.add_mtext(r"\A1;\pxqc;UP", dxfattribs={"layer": "TEXT"}).set_location(
        (label_x, label_y)
    )

    dxf_path = tmp_path / "synth_no_steps.dxf"
    doc.saveas(str(dxf_path))

    rep = load_drawing(dxf_path)
    anchors = detect_staircase_anchors(rep.document.modelspace())

    assert len(anchors) == 1
    a = anchors[0]
    assert a.tread_bbox_in is None, "No STEPS lines → tread_bbox_in must be None"
    # Position must be the label's position
    assert abs(a.x - label_x) < 1.0, f"Expected x≈{label_x}, got {a.x}"
    assert abs(a.y - label_y) < 1.0, f"Expected y≈{label_y}, got {a.y}"


def test_real_delhi_main_stair_has_tread_bbox() -> None:
    """Real Delhi file: at least one anchor near (211825, -104287) should have
    tread_bbox_in set and its centroid within ±50 of (211711, -104190).

    The expected centroid is based on the actual STEPS-layer geometry in the
    real fixture (measured during development).
    """
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    anchors = detect_staircase_anchors(rep.document.modelspace())

    # At least one anchor must have a tread bbox
    tread_anchors = [a for a in anchors if a.tread_bbox_in is not None]
    assert tread_anchors, (
        "Expected at least one anchor with tread_bbox_in set on the real Delhi file"
    )

    # The main staircase is the one closest to the expected centroid
    # (from inspection of the STEPS layer in the real DXF).
    expected_cx, expected_cy = 211711.0, -104190.0
    tolerance = 50.0

    matching = [
        a for a in tread_anchors
        if abs(a.x - expected_cx) <= tolerance and abs(a.y - expected_cy) <= tolerance
    ]
    assert matching, (
        f"No tread anchor near ({expected_cx}, {expected_cy}) ±{tolerance}. "
        f"Found tread anchors at: {[(a.x, a.y) for a in tread_anchors]}"
    )


def test_real_delhi_main_stair_area_from_tread_bbox() -> None:
    """End-to-end: parse the real Delhi file and verify that at least one
    STAIRCASE room has area > 3.7 sqm (the default-rect size) and its centroid
    is in the right neighbourhood after coordinate conversion.

    The real main stair bbox is ~195 × 141 inches ≈ 4.95m × 3.58m ≈ 17.7 sqm.
    We require at least one staircase with area > 10 sqm to confirm the tread
    bbox is being used instead of the 4×10ft default.
    """
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="test",
    )
    stair_rooms = [r for r in project.rooms if r.type == RoomType.staircase]
    assert stair_rooms, "Expected at least one STAIRCASE room"

    areas = [r.area_sqm for r in stair_rooms]
    # Default 4ft × 10ft rectangle = 1.219m × 3.048m ≈ 3.72 sqm.
    # With the tread bbox the main stair should be ~17 sqm.
    large_stairs = [a for a in areas if a > 10.0]
    assert large_stairs, (
        f"Expected at least one staircase with area > 10 sqm (got areas: {areas}). "
        "This suggests the tread bbox is not being used to size the staircase."
    )


def test_real_delhi_no_phantom_exterior_staircases() -> None:
    """End-to-end regression: lone UP/DN markers placed OUTSIDE the wall
    envelope (typically annotating an exterior step at an entrance) must not
    materialise into interior STAIRCASE rooms.

    The real Delhi fixture has two such phantom UP arrows at x ≈ 211504 — well
    west of the building's wall envelope (region.min_x ≈ 211580) — without any
    STEPS-layer tread geometry nearby. Before the fix these surfaced as
    floor-0 and floor-1 STAIRCASE rooms with their polygons partially outside
    the building. After the fix only the tread-backed interior staircases
    remain.
    """
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="test",
    )
    stair_rooms = [r for r in project.rooms if r.type == RoomType.staircase]
    # The phantom polygons live at negative-x in local-meter coords; their
    # min(x) sits below 0 (outside the west wall). All legitimate staircases
    # have polygons entirely at x ≥ 0.
    for room in stair_rooms:
        min_x = min(p.x for p in room.polygon)
        assert min_x >= 0.0, (
            f"Staircase {room.id!r} on floor {room.floor_level} extends "
            f"west of the building envelope (min x={min_x:.2f} m) — looks "
            f"like a phantom from an exterior UP/DN marker"
        )

    # And by count: exactly two real staircases (one per floor) survive.
    assert len(stair_rooms) == 2, (
        f"Expected exactly 2 tread-backed staircases (one per floor), got "
        f"{len(stair_rooms)}: "
        f"{[(r.floor_level, [(p.x, p.y) for p in r.polygon]) for r in stair_rooms]}"
    )
