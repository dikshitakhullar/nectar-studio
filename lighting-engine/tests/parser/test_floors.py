from lighting_engine.parser.floors import (
    FLOOR_LEVEL_MAP,
    FloorAnchor,
    detect_floor_anchors,
    floor_level_for_name,
    nearest_anchor_index,
)


def test_floor_level_for_name_maps_common_synonyms():
    assert floor_level_for_name("GROUND") == 0
    assert floor_level_for_name("GF") == 0
    assert floor_level_for_name("FIRST") == 1
    assert floor_level_for_name("FF") == 1
    assert floor_level_for_name("1ST") == 1
    assert floor_level_for_name("SECOND") == 2
    assert floor_level_for_name("BASEMENT") == -1
    assert floor_level_for_name("UNKNOWN") == 0  # safe default


def test_floor_level_map_is_case_insensitive_at_lookup():
    assert floor_level_for_name("ground") == 0
    assert floor_level_for_name("First") == 1


def test_nearest_anchor_index_picks_closest():
    anchors = [
        FloorAnchor(name="GROUND", x=0.0, y=0.0),
        FloorAnchor(name="FIRST", x=1000.0, y=0.0),
    ]
    assert nearest_anchor_index((10.0, 0.0), anchors) == 0
    assert nearest_anchor_index((990.0, 5.0), anchors) == 1


def test_detect_floor_anchors_finds_ground_and_first_floor_labels(tmp_path):
    import ezdxf
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_mtext(
        r"{\LGROUND FLOOR - FLOORING PLAN}", dxfattribs={"layer": "TEXT"}
    ).set_location((100.0, 200.0))
    msp.add_mtext(
        r"{\fArial|b1|i0|c0|p34;\LFIRST FLOOR - FURNITURE PLAN}",
        dxfattribs={"layer": "TEXT"},
    ).set_location((1200.0, 200.0))
    dxf_path = tmp_path / "floors.dxf"
    doc.saveas(str(dxf_path))

    import ezdxf as _ezdxf
    doc2 = _ezdxf.readfile(str(dxf_path))
    anchors = detect_floor_anchors(doc2.modelspace())
    names = {a.name for a in anchors}
    assert "GROUND" in names
    assert "FIRST" in names
    by_name = {a.name: (a.x, a.y) for a in anchors}
    assert by_name["GROUND"] == (100.0, 200.0)
    assert by_name["FIRST"] == (1200.0, 200.0)


def test_detect_floor_anchors_returns_empty_when_no_floor_labels(tmp_path):
    import ezdxf
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_mtext("LIVING ROOM", dxfattribs={"layer": "TEXT"}).set_location((0.0, 0.0))
    dxf_path = tmp_path / "no_floors.dxf"
    doc.saveas(str(dxf_path))

    import ezdxf as _ezdxf
    doc2 = _ezdxf.readfile(str(dxf_path))
    assert detect_floor_anchors(doc2.modelspace()) == []


def test_floor_level_map_contains_expected_names():
    # Spot-check the map is wired up
    assert FLOOR_LEVEL_MAP["GROUND"] == 0
    assert FLOOR_LEVEL_MAP["BASEMENT"] == -1
