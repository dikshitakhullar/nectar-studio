from pathlib import Path

import ezdxf as _ezdxf

from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.staircases import (
    cluster_staircase_labels,
    detect_staircase_anchors,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


def test_detect_up_and_dn_labels(tmp_path):
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
    # Centroid roughly between the two labels
    assert abs(a.x - 100.0) < 1.0
    assert 100.0 < a.y < 200.0


def test_only_up_label_still_counts_as_staircase(tmp_path):
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


def test_far_apart_labels_form_separate_clusters():
    # UP labels >300in apart should yield two clusters
    raw_positions = [
        ("UP", 100.0, 100.0),
        ("UP", 600.0, 100.0),  # 500 inches away — different staircase
    ]
    clusters = cluster_staircase_labels(raw_positions, max_distance_in=200.0)
    assert len(clusters) == 2


def test_close_labels_merge_into_one_cluster():
    raw_positions = [
        ("UP", 100.0, 100.0),
        ("DN", 150.0, 100.0),
        ("UP", 120.0, 150.0),
    ]
    clusters = cluster_staircase_labels(raw_positions, max_distance_in=200.0)
    assert len(clusters) == 1


def test_ignores_text_that_starts_with_up_or_dn_but_is_not_a_marker(tmp_path):
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


def test_real_delhi_file_detects_at_least_one_staircase():
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    anchors = detect_staircase_anchors(rep.document.modelspace())
    assert len(anchors) >= 1, (
        "real Delhi file has multiple UP/DN labels — should detect ≥1 staircase"
    )
