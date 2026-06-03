"""Tests for the furniture SVG renderer (Task 6.2)."""

from lighting_engine.brief.models import LightingLayer, Zone
from lighting_engine.models.geometry import Furniture, Point, Room, RoomType
from lighting_engine.render.furniture import render_furniture_svg


def _room_with_furniture() -> Room:
    room = Room(
        id="r",
        name="LIVING",
        type=RoomType.living,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=5, y=0),
            Point(x=5, y=4),
            Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
    )
    room.furniture.append(
        Furniture(
            id="s1",
            type="sofa",
            raw_label="sofa",
            position=Point(x=2.5, y=1.0),
        )
    )
    room.furniture.append(
        Furniture(
            id="ct",
            type="coffee_table",
            raw_label="coffee table",
            position=Point(x=2.5, y=2.0),
        )
    )
    return room


def test_furniture_svg_renders_well_formed_svg() -> None:
    room = _room_with_furniture()
    svg = render_furniture_svg(room, lamp_suggestions=[])
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert 'viewBox="' in svg


def test_furniture_svg_marks_each_furniture_item() -> None:
    room = _room_with_furniture()
    svg = render_furniture_svg(room, lamp_suggestions=[])
    # 2 furniture items → 2 furniture dots
    assert svg.count('class="furniture-dot"') == 2


def test_furniture_svg_renders_lamp_suggestion_triangles() -> None:
    room = _room_with_furniture()
    lamps = [
        Zone(
            layer=LightingLayer.accent,
            purpose="reading corner",
            cct_k=3000,
            cri_min=90,
            fixture_type="floor_lamp",
            position_hint="wall N",
        ),
    ]
    svg = render_furniture_svg(room, lamp_suggestions=lamps)
    assert 'class="lamp-floor"' in svg
    assert "reading corner" in svg


def test_furniture_svg_table_lamp_uses_table_class() -> None:
    """A `table_lamp` fixture_type should render with the lamp-table CSS class."""
    room = _room_with_furniture()
    lamps = [
        Zone(
            layer=LightingLayer.decorative,
            purpose="side table glow",
            cct_k=2700,
            cri_min=90,
            fixture_type="table_lamp",
            position_hint="beside sofa",
        ),
    ]
    svg = render_furniture_svg(room, lamp_suggestions=lamps)
    assert 'class="lamp-table"' in svg


def test_furniture_svg_unknown_lamp_fixture_type_falls_back_to_ambient() -> None:
    """Edge case: a fixture_type the renderer doesn't recognise should render
    via an ambient-style fallback class rather than crashing or emitting an
    empty class."""
    room = _room_with_furniture()
    lamps = [
        Zone(
            layer=LightingLayer.ambient,
            purpose="corner fill",
            cct_k=2700,
            cri_min=90,
            fixture_type="strip",  # not a lamp archetype
            position_hint="corner",
        ),
    ]
    svg = render_furniture_svg(room, lamp_suggestions=lamps)
    assert 'class="lamp-ambient"' in svg


def test_furniture_svg_with_no_furniture_still_renders_polygon() -> None:
    room = Room(
        id="r",
        name="EMPTY",
        type=RoomType.unknown,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=3, y=0),
            Point(x=3, y=3),
            Point(x=0, y=3),
        ],
        ceiling_height_m=2.7,
    )
    svg = render_furniture_svg(room, lamp_suggestions=[])
    assert "<polygon" in svg
    # CSS rule for .furniture-dot still exists in <style>, but no instance is drawn.
    assert 'class="furniture-dot"' not in svg


def test_furniture_svg_handles_triangle_room() -> None:
    room = Room(
        id="tri",
        name="ALCOVE",
        type=RoomType.unknown,
        floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=4, y=0), Point(x=2, y=3)],
        ceiling_height_m=2.7,
    )
    svg = render_furniture_svg(room, lamp_suggestions=[])
    assert "<polygon" in svg


def test_furniture_svg_handles_pentagon_room() -> None:
    room = Room(
        id="pent",
        name="NOOK",
        type=RoomType.unknown,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=4, y=0),
            Point(x=5, y=2),
            Point(x=2, y=4),
            Point(x=0, y=2),
        ],
        ceiling_height_m=2.7,
    )
    svg = render_furniture_svg(room, lamp_suggestions=[])
    assert "<polygon" in svg


def test_furniture_svg_handles_small_room_under_one_meter() -> None:
    room = Room(
        id="tiny",
        name="POWDER",
        type=RoomType.unknown,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=0.6, y=0),
            Point(x=0.6, y=0.8),
            Point(x=0, y=0.8),
        ],
        ceiling_height_m=2.4,
    )
    svg = render_furniture_svg(room, lamp_suggestions=[])
    assert svg.startswith("<svg")
    assert "viewBox=\"0 0 -" not in svg


def test_furniture_svg_handles_very_large_room() -> None:
    room = Room(
        id="big",
        name="HALL",
        type=RoomType.unknown,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=25, y=0),
            Point(x=25, y=22),
            Point(x=0, y=22),
        ],
        ceiling_height_m=3.5,
    )
    svg = render_furniture_svg(room, lamp_suggestions=[])
    assert svg.startswith("<svg")
    assert 'width="1350"' in svg
    assert 'height="1200"' in svg


def test_furniture_svg_escapes_html_in_purpose_and_name() -> None:
    """HTML metacharacters in lamp purpose or room name must be escaped."""
    room = Room(
        id="r",
        name="STUDY & READING <NOOK>",
        type=RoomType.study,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=4, y=0),
            Point(x=4, y=3),
            Point(x=0, y=3),
        ],
        ceiling_height_m=2.7,
    )
    lamps = [
        Zone(
            layer=LightingLayer.accent,
            purpose="reading <chair> & ottoman",
            cct_k=2700,
            cri_min=90,
            fixture_type="floor_lamp",
            position_hint="corner",
        ),
    ]
    svg = render_furniture_svg(room, lamp_suggestions=lamps)
    assert "&amp;" in svg
    assert "&lt;chair&gt;" in svg
    assert "&lt;NOOK&gt;" in svg
    assert "<chair>" not in svg
    assert "<NOOK>" not in svg


def test_furniture_svg_escapes_html_in_furniture_label() -> None:
    """Furniture raw_label / type values are user-supplied — must be escaped."""
    room = Room(
        id="r",
        name="STUDY",
        type=RoomType.study,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=4, y=0),
            Point(x=4, y=3),
            Point(x=0, y=3),
        ],
        ceiling_height_m=2.7,
    )
    room.furniture.append(
        Furniture(
            id="d1",
            type="desk",
            raw_label="<DESK> & CHAIR",
            position=Point(x=2.0, y=1.5),
        )
    )
    svg = render_furniture_svg(room, lamp_suggestions=[])
    assert "&lt;DESK&gt;" in svg
    assert "&amp;" in svg
    assert "<DESK>" not in svg
