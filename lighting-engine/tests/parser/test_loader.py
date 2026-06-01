from pathlib import Path

import pytest

from lighting_engine.parser.loader import LoadReport, load_drawing  # noqa: F401

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


def test_loads_clean_dxf():
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    assert rep.document is not None
    assert rep.merges == 0
    assert rep.source_format == "dxf"
    # Spot check: there are walls in the modelspace
    msp = rep.document.modelspace()
    walls = [e for e in msp if e.dxf.layer == "WALL"]
    assert len(walls) > 100


def test_loads_dwg_via_libredwg_and_sanitizes():
    # real_furniture.dwg → conversion produces a broken DXF; sanitizer must rescue it
    rep = load_drawing(FIXTURES / "real_furniture.dwg")
    assert rep.document is not None
    assert rep.source_format == "dwg"
    # We know the furniture file requires at least one merge to parse
    assert rep.merges >= 1


def test_missing_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        load_drawing(FIXTURES / "does_not_exist.dwg")


def test_load_report_records_insunits_from_header():
    # The real Delhi DWG uses INSUNITS=1 (inches)
    rep = load_drawing(FIXTURES / "real_base_architectural.dxf")
    assert rep.insunits == 1


def test_strict_units_raises_for_non_inch_files(tmp_path):
    # Construct a DXF with INSUNITS=4 (millimetres) and confirm strict mode rejects it
    import ezdxf as _ezdxf
    doc = _ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 4
    dxf_path = tmp_path / "mm.dxf"
    doc.saveas(str(dxf_path))
    with pytest.raises(ValueError, match="INSUNITS"):
        load_drawing(dxf_path, strict_units=True)
    # But non-strict mode loads it and records insunits=4
    rep = load_drawing(dxf_path, strict_units=False)
    assert rep.insunits == 4
