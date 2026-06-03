import xml.etree.ElementTree as ET
from pathlib import Path

from lighting_engine.parser.pipeline import parse_file
from scripts.visualize_parse import render_svg

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


def test_render_svg_produces_well_formed_svg_for_real_file(tmp_path):
    project, _ = parse_file(FIXTURES / "real_base_architectural.dxf", project_name="x")
    out = tmp_path / "out.svg"
    render_svg(
        project=project,
        dxf_path=FIXTURES / "real_base_architectural.dxf",
        output_path=out,
    )
    assert out.exists()
    # Confirm it's valid XML and has the expected groups
    root = ET.parse(out).getroot()
    assert root.tag.endswith("svg")
    groups = [g.get("class") for g in root.iter("{http://www.w3.org/2000/svg}g")]
    # We expect group classes for walls, rooms, doors, fixtures
    assert "walls" in groups
    assert "rooms" in groups
    assert "doors" in groups
    assert "fixtures" in groups


def test_render_svg_includes_door_arc_glyphs_for_real_file(tmp_path):
    """The Delhi file's parsed doors must appear as `door-arc` glyphs in the
    SVG. Without this, the visualiser cannot show what the door detector
    found (the primary debugging aid for the upcoming room-anchor pass).
    """
    project, _ = parse_file(FIXTURES / "real_base_architectural.dxf", project_name="x")
    out = tmp_path / "out.svg"
    render_svg(
        project=project,
        dxf_path=FIXTURES / "real_base_architectural.dxf",
        output_path=out,
    )
    text = out.read_text()
    # Many doors → many door-arc glyphs. A path is the natural SVG primitive
    # for an arc, but circles also work — assert against the CSS class.
    assert "door-arc" in text, "expected door-arc glyphs in the rendered SVG"
    assert text.count("door-arc") >= 10, (
        f"expected many door-arc glyphs in Delhi SVG, got "
        f"{text.count('door-arc')}"
    )
