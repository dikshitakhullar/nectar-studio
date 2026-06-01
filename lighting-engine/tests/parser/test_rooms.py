from pathlib import Path

from lighting_engine.parser.geometry import find_plan_region
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.rooms import (
    extract_rooms,
    infer_room_type,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"
INCH_TO_M = 0.0254


def _wall_segments(msp) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for e in msp.query("LINE"):
        if e.dxf.layer != "WALL":
            continue
        out.append((
            (float(e.dxf.start.x), float(e.dxf.start.y)),
            (float(e.dxf.end.x), float(e.dxf.end.y)),
        ))
    return out


def test_infer_room_type_from_name():
    assert infer_room_type("MASTER BEDROOM").value == "bedroom"
    assert infer_room_type("BEDROOM - 1").value == "bedroom"
    assert infer_room_type("MASTER TOILET").value == "bathroom"
    assert infer_room_type("TOILET - 2").value == "bathroom"
    assert infer_room_type("STUDY ROOM").value == "study"
    assert infer_room_type("KITCHEN").value == "kitchen"
    assert infer_room_type("LIVING").value == "living"
    assert infer_room_type("DINING").value == "dining"
    assert infer_room_type("FOYER").value == "foyer"
    assert infer_room_type("LOBBY").value == "hallway"
    assert infer_room_type("DOUBLE HEIGHT FOYER").value == "foyer"
    assert infer_room_type("BALCONY").value == "outdoor"
    assert infer_room_type("MYSTERY ROOM").value == "unknown"


def test_extract_rooms_snaps_to_real_walls_when_label_is_centered(tmp_path):
    """A 120-inch square of walls + a centered label whose nominal dims roughly
    match should produce a Room polygon that snaps to those walls."""
    import ezdxf

    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    if "WALL" not in doc.layers:
        doc.layers.add("WALL")
    # 120in × 120in (= 10ft × 10ft) square of walls
    msp.add_line((0, 0), (120, 0), dxfattribs={"layer": "WALL"})
    msp.add_line((120, 0), (120, 120), dxfattribs={"layer": "WALL"})
    msp.add_line((120, 120), (0, 120), dxfattribs={"layer": "WALL"})
    msp.add_line((0, 120), (0, 0), dxfattribs={"layer": "WALL"})
    # Centered label declaring 10ft × 10ft (matches actual wall extent)
    msp.add_mtext(
        r"\A1;\pxqc;TEST ROOM | 10'-0\" x 10'-0\"", dxfattribs={"layer": "TEXT"}
    ).set_location((60, 60))
    dxf_path = tmp_path / "synth.dxf"
    doc.saveas(str(dxf_path))

    rep = load_drawing(dxf_path, strict_units=False)
    msp2 = rep.document.modelspace()
    segs = _wall_segments(msp2)
    region = find_plan_region([((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in segs])
    result = extract_rooms(msp2, region, segs, dxf_unit_to_m=INCH_TO_M)

    assert len(result.rooms) == 1
    room = result.rooms[0]
    assert room.name == "TEST ROOM"
    # Ray-cast hits all 4 walls (each 60in from label, half-nom 60in → ratio 1.0)
    # → polygon snaps exactly to the wall square: 120*120 sq-in → 9.290 sqm
    expected_sqm = (120 * INCH_TO_M) ** 2
    assert abs(room.area_sqm - expected_sqm) < 0.01
    # All 4 sides snapped → not a fallback
    assert result.rect_fallback_room_ids == []


def test_extract_rooms_falls_back_to_label_rect_when_no_walls_in_range(tmp_path):
    """With no walls in the cardinal directions from the label, the room
    polygon falls back to the nominal label rect AND is flagged."""
    import ezdxf

    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_mtext(
        r"\A1;\pxqc;ISOLATED | 10'-0\" x 8'-0\"", dxfattribs={"layer": "TEXT"}
    ).set_location((100, 100))
    # Two stray wall lines far away — they exist for the plan-region detector
    # but are well outside the ray-cast search range from (100, 100).
    if "WALL" not in doc.layers:
        doc.layers.add("WALL")
    msp.add_line((900, 900), (901, 900), dxfattribs={"layer": "WALL"})
    msp.add_line((900, 900), (900, 901), dxfattribs={"layer": "WALL"})
    dxf_path = tmp_path / "synth_no_walls.dxf"
    doc.saveas(str(dxf_path))

    rep = load_drawing(dxf_path, strict_units=False)
    msp2 = rep.document.modelspace()
    segs = _wall_segments(msp2)
    region = find_plan_region(
        [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in segs]
        + [(100.0, 100.0)]
    )
    result = extract_rooms(msp2, region, segs, dxf_unit_to_m=INCH_TO_M)

    assert len(result.rooms) == 1
    assert result.rect_fallback_room_ids == [result.rooms[0].id]
    # Polygon dims match the nominal label (10ft x 8ft)
    room = result.rooms[0]
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    assert abs((max(xs) - min(xs)) - (10 * 12 * INCH_TO_M)) < 1e-6
    assert abs((max(ys) - min(ys)) - (8 * 12 * INCH_TO_M)) < 1e-6


def test_extract_rooms_segments_two_floors_in_one_dwg(tmp_path):
    """A DWG with GROUND + FIRST FLOOR labels should produce Rooms tagged by floor."""
    import ezdxf

    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    if "WALL" not in doc.layers:
        doc.layers.add("WALL")
    # Ground floor: 120-inch square + label near (0, 0)
    for a, b in [((0, 0), (120, 0)), ((120, 0), (120, 120)),
                 ((120, 120), (0, 120)), ((0, 120), (0, 0))]:
        msp.add_line(a, b, dxfattribs={"layer": "WALL"})
    msp.add_mtext(
        r"\A1;\pxqc;LIVING | 5'-0\" x 5'-0\"", dxfattribs={"layer": "TEXT"}
    ).set_location((60, 60))
    msp.add_mtext(
        r"{\LGROUND FLOOR}", dxfattribs={"layer": "TEXT"}
    ).set_location((60, -30))
    # First floor: another 120-inch square at x_offset 500
    for a, b in [((500, 0), (620, 0)), ((620, 0), (620, 120)),
                 ((620, 120), (500, 120)), ((500, 120), (500, 0))]:
        msp.add_line(a, b, dxfattribs={"layer": "WALL"})
    msp.add_mtext(
        r"\A1;\pxqc;BEDROOM | 5'-0\" x 5'-0\"", dxfattribs={"layer": "TEXT"}
    ).set_location((560, 60))
    msp.add_mtext(
        r"{\LFIRST FLOOR}", dxfattribs={"layer": "TEXT"}
    ).set_location((560, -30))
    dxf_path = tmp_path / "two_floors.dxf"
    doc.saveas(str(dxf_path))

    rep = load_drawing(dxf_path, strict_units=False)
    msp2 = rep.document.modelspace()
    segs = _wall_segments(msp2)
    region = find_plan_region([((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in segs])
    result = extract_rooms(msp2, region, segs, dxf_unit_to_m=INCH_TO_M)

    by_floor: dict[int, list[str]] = {}
    for r in result.rooms:
        by_floor.setdefault(r.floor_level, []).append(r.name)
    assert 0 in by_floor and 1 in by_floor, f"got floors {set(by_floor)}"
    assert "LIVING" in by_floor[0]
    assert "BEDROOM" in by_floor[1]


def test_extract_rooms_on_real_delhi_file_meets_checkpoint_a():
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf", strict_units=False)
    msp = rep.document.modelspace()
    segs = _wall_segments(msp)
    region = find_plan_region([((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in segs])
    result = extract_rooms(msp, region, segs, dxf_unit_to_m=INCH_TO_M)

    names = {r.name for r in result.rooms}
    expected_subset = {
        "MASTER BEDROOM", "STUDY ROOM", "BEDROOM - 1", "BEDROOM - 2",
        "MASTER TOILET", "LOBBY",
    }
    missing = expected_subset - names
    assert not missing, f"expected rooms not found: {missing}"
    # Checkpoint A: at least 10 rooms extracted
    assert len(result.rooms) >= 10
    # Every room has a usable polygon
    for r in result.rooms:
        assert len(r.polygon) >= 3
        # Shafts and small utility spaces can be < 0.5 sqm; still require > 0 sqm.
        # The 0.1 sqm floor catches truly degenerate (zero-area) polygons.
        assert r.area_sqm > 0.1, f"{r.name} has area {r.area_sqm:.4f} sqm (degenerate polygon?)"
    # Most rooms should anchor to at least 2 real walls (not pure fallback)
    fallback_ratio = len(result.rect_fallback_room_ids) / len(result.rooms)
    assert fallback_ratio < 0.7, (
        f"{fallback_ratio:.0%} of rooms fell back to label-rect — wall-snapping is unhealthy"
    )
    # Quality check: for known rooms whose names match exactly, the polygon
    # bounding box should be within ±40% of the nominal label dimensions.
    # Generous bound because ray-cast can over- or under-shoot when walls are
    # sparse on one side; we want to catch egregious mismatches, not perfection.
    nominal_dims_m = {
        "STUDY ROOM":     (22 * 12 * INCH_TO_M, 17 * 12 * INCH_TO_M),  # 22×16'9"
        "BEDROOM - 2":    (22 * 12 * INCH_TO_M, 17 * 12 * INCH_TO_M),  # 21'9"×16'9"
        "MASTER BEDROOM": (24 * 12 * INCH_TO_M, 21 * 12 * INCH_TO_M),  # ~24×21 ft
    }
    by_name = {r.name: r for r in result.rooms}
    for name, (nom_w, nom_h) in nominal_dims_m.items():
        if name not in by_name:
            continue
        r = by_name[name]
        xs = [p.x for p in r.polygon]
        ys = [p.y for p in r.polygon]
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)
        long_p, short_p = max(bw, bh), min(bw, bh)
        long_n, short_n = max(nom_w, nom_h), min(nom_w, nom_h)
        assert 0.6 * long_n <= long_p <= 1.4 * long_n, (
            f"{name} long side {long_p:.2f}m off from nominal {long_n:.2f}m by >40%"
        )
        assert 0.6 * short_n <= short_p <= 1.4 * short_n, (
            f"{name} short side {short_p:.2f}m off from nominal {short_n:.2f}m by >40%"
        )
