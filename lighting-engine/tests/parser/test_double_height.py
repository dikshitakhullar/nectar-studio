"""Tests for double-height (open-to-below) region detection.

Two flavours of test here:

1. End-to-end against the real Delhi architectural DXF — the user identified
   the drawing room, entrance foyer, and a void next to the courtyard as
   double-height in the source plan. We require the detector to attach a
   polygon to at least two of these rooms via the pipeline.

2. A synthetic DXF with one solid square (room) and one dashed square inside
   it — the detector must find exactly one polygon and the pipeline must
   attach it to the only room.
"""

from pathlib import Path

import ezdxf

from lighting_engine.parser.double_height import (
    collect_linetype_summary,
    find_double_height_polygons,
)
from lighting_engine.parser.geometry import find_plan_region
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.pipeline import parse_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"
INCH_TO_M = 0.0254


# ---------------------------------------------------------------------------
# End-to-end: real Delhi fixture
# ---------------------------------------------------------------------------


def test_real_delhi_detector_finds_dotted_polygons_before_room_attachment():
    """Standalone detector should find several non-continuous closed regions."""
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    doc = rep.document
    # Use the same wall-centroid plan-region detection the pipeline uses
    msp = doc.modelspace()
    wall_centroids: list[tuple[float, float]] = []
    for e in msp.query("LINE"):
        if e.dxf.layer == "WALL":
            wall_centroids.append((
                (float(e.dxf.start.x) + float(e.dxf.end.x)) / 2,
                (float(e.dxf.start.y) + float(e.dxf.end.y)) / 2,
            ))
    region = find_plan_region(wall_centroids)
    polygons = find_double_height_polygons(doc, region, dxf_unit_to_m=INCH_TO_M)
    # The Delhi plan draws double-height voids over the drawing room, the
    # entrance foyer, and a courtyard-adjacent void. We expect at least 3
    # polygons (and in practice get 8–10 because the fixture is a multi-sheet
    # DXF with duplicated dotted geometry across sheets).
    assert len(polygons) >= 3, (
        f"detector found only {len(polygons)} dotted polygons; "
        "expected at least 3 from the Delhi fixture"
    )
    # Every detected polygon should be a closed ring of >= 3 distinct points
    # in the local-meter frame.
    for poly in polygons:
        assert len(poly) >= 3


def test_real_delhi_linetype_summary_reports_hidden():
    """The Delhi fixture uses 'HIDDEN' as its non-continuous linetype.

    If a future fixture introduces dashed/dashdot/phantom linetypes we want
    them surfaced here so the detector can be tuned if needed.
    """
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    summary = collect_linetype_summary(rep.document)
    non_continuous = {
        lt: n for lt, n in summary.items()
        if lt.upper() not in {"CONTINUOUS", "BYBLOCK", ""}
    }
    assert non_continuous, "expected the Delhi fixture to contain dotted geometry"
    # We expect HIDDEN specifically — the fixture's only non-continuous
    # linetype is `HIDDEN` (case-sensitive in the source file).
    assert any(lt.upper() == "HIDDEN" for lt in non_continuous), (
        f"expected HIDDEN linetype, got: {sorted(non_continuous)}"
    )


def test_real_delhi_pipeline_tags_drawing_room_and_at_least_one_other():
    """End-to-end: parse the Delhi fixture and verify drawing room (or its
    foyer neighbours) get tagged with at least one double-height polygon."""
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="Mohak Residence",
    )
    tagged = {
        r.name: len(r.double_height_polygons)
        for r in project.rooms if r.double_height_polygons
    }
    assert tagged, "expected at least one room to be tagged as double-height"
    # User-confirmed: top half of drawing room is double-height; part of
    # entrance foyer is too. Require at least 2 distinct rooms tagged.
    assert len(tagged) >= 2, (
        f"expected ≥2 rooms tagged as double-height, got: {tagged}"
    )
    # Spot check: the drawing room should be among the tagged rooms (it's
    # one of the strongest signals in this plan).
    upper_names = {n.upper() for n in tagged}
    assert any("DRAWING" in n for n in upper_names), (
        f"expected the DRAWING ROOM to be tagged; got: {tagged}"
    )


# ---------------------------------------------------------------------------
# Synthetic: 1 solid square + 1 dashed square inside it
# ---------------------------------------------------------------------------


def _build_synthetic_dxf_with_dashed_inner_square(tmp_path: Path) -> Path:
    """One solid 120in × 120in room with a 48in × 48in HIDDEN square inside."""
    doc = ezdxf.new(setup=True)
    # Strict-units mode rejects non-inch INSUNITS — match the production
    # fixture (INSUNITS=1 = inches) so `parse_file` accepts the synthetic.
    doc.header["$INSUNITS"] = 1
    msp = doc.modelspace()
    if "WALL" not in doc.layers:
        doc.layers.add("WALL")
    if "VOID" not in doc.layers:
        doc.layers.add("VOID")

    # Solid wall square (CONTINUOUS by default)
    for a, b in [
        ((0, 0), (120, 0)),
        ((120, 0), (120, 120)),
        ((120, 120), (0, 120)),
        ((0, 120), (0, 0)),
    ]:
        msp.add_line(a, b, dxfattribs={"layer": "WALL"})

    # Inner dashed square — explicitly set linetype to HIDDEN on each line so
    # we don't depend on the layer's default.
    for a, b in [
        ((36, 36), (84, 36)),
        ((84, 36), (84, 84)),
        ((84, 84), (36, 84)),
        ((36, 84), (36, 36)),
    ]:
        msp.add_line(a, b, dxfattribs={"layer": "VOID", "linetype": "HIDDEN"})

    # Room label — required so the pipeline produces a Room for attachment.
    msp.add_mtext(
        r"\A1;\pxqc;LIVING | 10'-0\" x 10'-0\"",
        dxfattribs={"layer": "TEXT"},
    ).set_location((60, 60))

    dxf_path = tmp_path / "synth_double_height.dxf"
    doc.saveas(str(dxf_path))
    return dxf_path


def test_synthetic_detector_finds_inner_dashed_square(tmp_path: Path):
    dxf_path = _build_synthetic_dxf_with_dashed_inner_square(tmp_path)
    rep = load_drawing(dxf_path, strict_units=False)
    doc = rep.document
    msp = doc.modelspace()
    wall_centroids: list[tuple[float, float]] = []
    for e in msp.query("LINE"):
        if e.dxf.layer == "WALL":
            wall_centroids.append((
                (float(e.dxf.start.x) + float(e.dxf.end.x)) / 2,
                (float(e.dxf.start.y) + float(e.dxf.end.y)) / 2,
            ))
    region = find_plan_region(wall_centroids)
    polygons = find_double_height_polygons(doc, region, dxf_unit_to_m=INCH_TO_M)
    assert len(polygons) == 1, f"expected exactly 1 dotted polygon, got {len(polygons)}"
    # The polygon should be roughly the area of the inner 48×48 square:
    # 48 in × 48 in ≈ 1.488 sqm. Compute via shoelace.
    poly = polygons[0]
    n = len(poly)
    s = 0.0
    for i in range(n):
        x1, y1 = poly[i].x, poly[i].y
        x2, y2 = poly[(i + 1) % n].x, poly[(i + 1) % n].y
        s += x1 * y2 - x2 * y1
    area_sqm = abs(s) / 2.0
    expected_sqm = (48 * INCH_TO_M) ** 2
    assert abs(area_sqm - expected_sqm) < 0.05, (
        f"polygon area {area_sqm:.3f} != expected {expected_sqm:.3f}"
    )


def test_synthetic_pipeline_attaches_polygon_to_room(tmp_path: Path):
    dxf_path = _build_synthetic_dxf_with_dashed_inner_square(tmp_path)
    project, _ = parse_file(dxf_path, project_name="synth")
    rooms_with_dh = [r for r in project.rooms if r.double_height_polygons]
    assert len(rooms_with_dh) == 1
    assert rooms_with_dh[0].name == "LIVING"
    assert len(rooms_with_dh[0].double_height_polygons) == 1
