"""Tests for door-position detection from DWG primitives.

Doors are precisely drawn in residential DWGs because contractors need exact
positions — but the architect may draw them as a block INSERT, a swing ARC, or
a paired pair of LINE/LWPOLYLINE swing-symbol strokes. This module's
collector must surface all three patterns as ``DoorRaw`` records so the
downstream attachment step (and the planned room-anchor pass) has the data
it needs.

Coordinates supplied by callers are in DXF units; results come back in the
local-meter frame matching ``PlanRegion``.
"""

from pathlib import Path

import ezdxf

from lighting_engine.parser.door_detection import DoorRaw, collect_door_positions
from lighting_engine.parser.geometry import PlanRegion, find_plan_region
from lighting_engine.parser.layers import LayerRole, classify_layers
from lighting_engine.parser.loader import load_drawing

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"
INCH_TO_M = 0.0254

_DELHI_DXF = FIXTURES / "real_base_architectural.dxf"


def _full_region() -> PlanRegion:
    """A trivially-large PlanRegion that contains any reasonable test point."""
    return PlanRegion(
        min_x=-1_000_000.0,
        min_y=-1_000_000.0,
        max_x=1_000_000.0,
        max_y=1_000_000.0,
        outliers_rejected=0,
    )


def test_doorraw_is_frozen():
    """DoorRaw must be a frozen dataclass — collectors must not mutate records."""
    raw = DoorRaw(
        position=(1.0, 2.0),
        swing_radius_m=0.9,
        swing_orientation_deg=45.0,
        source_layer="DOOR",
    )
    try:
        raw.position = (3.0, 4.0)  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("DoorRaw must be frozen")


def test_insert_on_door_layer_detected():
    """One INSERT on a door layer yields one DoorRaw at the insert position."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1
    if "DOOR" not in doc.layers:
        doc.layers.add("DOOR")
    if "DOOR_BLK" not in doc.blocks:
        blk = doc.blocks.new(name="DOOR_BLK")
        blk.add_line((0, 0), (1, 0))
    msp = doc.modelspace()
    msp.add_blockref("DOOR_BLK", (100.0, 200.0), dxfattribs={"layer": "DOOR"})

    result = collect_door_positions(
        msp,
        door_layers={"DOOR"},
        region=_full_region(),
        dxf_unit_to_m=INCH_TO_M,
    )

    assert len(result) == 1
    door = result[0]
    # Position is in local meters: (100 - (-1e6)) * 0.0254 ≈ 25_402.54
    expected_x = (100.0 - (-1_000_000.0)) * INCH_TO_M
    expected_y = (200.0 - (-1_000_000.0)) * INCH_TO_M
    assert door.position == (expected_x, expected_y)
    assert door.swing_radius_m is None
    assert door.swing_orientation_deg is None
    assert door.source_layer == "DOOR"


def test_arc_on_door_layer_detected_with_swing_data():
    """An ARC on a door layer yields one DoorRaw at the chord midpoint, with
    swing_radius and orientation populated from the arc geometry."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1
    if "DOOR" not in doc.layers:
        doc.layers.add("DOOR")
    msp = doc.modelspace()
    # Quarter-arc from 0° to 90° centred at (50, 50) with radius 30.
    # Start point: (80, 50). End point: (50, 80). Chord midpoint: (65, 65).
    msp.add_arc(
        center=(50.0, 50.0),
        radius=30.0,
        start_angle=0.0,
        end_angle=90.0,
        dxfattribs={"layer": "DOOR"},
    )

    result = collect_door_positions(
        msp,
        door_layers={"DOOR"},
        region=_full_region(),
        dxf_unit_to_m=INCH_TO_M,
    )

    assert len(result) == 1
    door = result[0]
    expected_chord_mid_x = (65.0 - (-1_000_000.0)) * INCH_TO_M
    expected_chord_mid_y = (65.0 - (-1_000_000.0)) * INCH_TO_M
    assert abs(door.position[0] - expected_chord_mid_x) < 1e-6
    assert abs(door.position[1] - expected_chord_mid_y) < 1e-6
    assert door.swing_radius_m is not None
    assert abs(door.swing_radius_m - 30.0 * INCH_TO_M) < 1e-6
    # Mid-angle of 0..90 is 45°
    assert door.swing_orientation_deg is not None
    assert abs(door.swing_orientation_deg - 45.0) < 1e-6
    assert door.source_layer == "DOOR"


def test_line_pair_on_door_layer_detected_as_single_door():
    """Two nearby LINEs on a door layer (swing-leaf + chord pattern) yield
    exactly one DoorRaw at the midpoint of the pair."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1
    if "DOOR" not in doc.layers:
        doc.layers.add("DOOR")
    msp = doc.modelspace()
    # Two parallel short LINEs ~5 in apart (well under the 0.5m / ~20 in
    # pairing radius). Architect's typical swing-symbol stroke pair.
    msp.add_line((100.0, 200.0), (110.0, 200.0), dxfattribs={"layer": "DOOR"})
    msp.add_line((100.0, 205.0), (110.0, 205.0), dxfattribs={"layer": "DOOR"})

    result = collect_door_positions(
        msp,
        door_layers={"DOOR"},
        region=_full_region(),
        dxf_unit_to_m=INCH_TO_M,
    )

    assert len(result) == 1
    door = result[0]
    # Midpoint of the four endpoints = (105, 202.5)
    expected_x = (105.0 - (-1_000_000.0)) * INCH_TO_M
    expected_y = (202.5 - (-1_000_000.0)) * INCH_TO_M
    assert abs(door.position[0] - expected_x) < 1e-6
    assert abs(door.position[1] - expected_y) < 1e-6
    assert door.swing_radius_m is None
    assert door.swing_orientation_deg is None


def test_entities_outside_region_skipped():
    """Entities whose source-DXF position sits outside the PlanRegion bbox
    are dropped before any conversion."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1
    if "DOOR" not in doc.layers:
        doc.layers.add("DOOR")
    if "DOOR_BLK" not in doc.blocks:
        blk = doc.blocks.new(name="DOOR_BLK")
        blk.add_line((0, 0), (1, 0))
    msp = doc.modelspace()
    msp.add_blockref("DOOR_BLK", (5_000.0, 5_000.0), dxfattribs={"layer": "DOOR"})

    region = PlanRegion(min_x=0.0, min_y=0.0, max_x=100.0, max_y=100.0,
                       outliers_rejected=0)
    result = collect_door_positions(
        msp,
        door_layers={"DOOR"},
        region=region,
        dxf_unit_to_m=INCH_TO_M,
    )

    assert result == []


def test_entities_on_non_door_layers_ignored():
    """Entities on layers not in door_layers must be ignored entirely."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1
    if "WALL" not in doc.layers:
        doc.layers.add("WALL")
    msp = doc.modelspace()
    msp.add_arc(
        center=(50.0, 50.0), radius=30.0,
        start_angle=0.0, end_angle=90.0,
        dxfattribs={"layer": "WALL"},
    )
    msp.add_line((100.0, 200.0), (110.0, 200.0), dxfattribs={"layer": "WALL"})
    msp.add_line((100.0, 205.0), (110.0, 205.0), dxfattribs={"layer": "WALL"})

    result = collect_door_positions(
        msp,
        door_layers={"DOOR"},
        region=_full_region(),
        dxf_unit_to_m=INCH_TO_M,
    )

    assert result == []


# ---------------------------------------------------------------------------
# Real Delhi fixture
# ---------------------------------------------------------------------------


def test_real_delhi_detects_many_doors():
    """On the Delhi file we expect a healthy door count from ARC + INSERT +
    LWPOLYLINE-pair patterns combined. The file has 45 INSERTs and 4 ARCs on
    the DOOR layer plus 8 LWPOLYLINEs that pair into 4 doors. We expect at
    LEAST 30 detected (allowing for some clustering of duplicated symbols).
    """
    rep = load_drawing(_DELHI_DXF)
    doc = rep.document
    msp = doc.modelspace()
    layer_roles = classify_layers([layer.dxf.name for layer in doc.layers])
    door_layers = set(layer_roles.get(LayerRole.door, []))
    assert door_layers, "Delhi fixture must classify some layers as doors"

    # Compute the plan region from wall centroids — same as pipeline.
    wall_layers = set(layer_roles.get(LayerRole.wall, []))
    wall_centroids = [
        (
            (float(e.dxf.start.x) + float(e.dxf.end.x)) / 2,
            (float(e.dxf.start.y) + float(e.dxf.end.y)) / 2,
        )
        for e in msp.query("LINE") if e.dxf.layer in wall_layers
    ]
    region = find_plan_region(wall_centroids)

    result = collect_door_positions(
        msp,
        door_layers=door_layers,
        region=region,
        dxf_unit_to_m=INCH_TO_M,
    )

    assert len(result) >= 30, (
        f"expected >=30 doors detected on the Delhi fixture, got {len(result)}"
    )
    # And of those, at least a handful should carry arc-derived swing data.
    with_arcs = [d for d in result if d.swing_radius_m is not None]
    assert len(with_arcs) >= 2, (
        f"expected at least 2 doors with arc-derived swing geometry, "
        f"got {len(with_arcs)}"
    )
