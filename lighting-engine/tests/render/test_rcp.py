"""Tests for the RCP SVG renderer (Task 6.1)."""

from lighting_engine.models.geometry import (
    Fixture,
    FixtureSource,
    LightingLayer,
    Point,
    Room,
    RoomType,
)
from lighting_engine.render.rcp import render_rcp_svg


def _room_with_fixtures() -> tuple[Room, list[Fixture]]:
    room = Room(
        id="r",
        name="DINING",
        type=RoomType.dining,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=5, y=0),
            Point(x=5, y=4),
            Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
    )
    fixtures = [
        Fixture(
            id="a1",
            type="downlight",
            position=Point(x=1.25, y=1.0),
            source=FixtureSource.proposed,
            layer=LightingLayer.ambient,
            wattage_w=12,
            lumens=1500,
            cct_k=2700,
            cri=90,
            beam_angle_deg=60,
        ),
        Fixture(
            id="t1",
            type="pendant",
            position=Point(x=2.5, y=2.0),
            source=FixtureSource.proposed,
            layer=LightingLayer.task,
            wattage_w=15,
            lumens=1500,
            cct_k=2700,
            cri=90,
            beam_angle_deg=30,
        ),
    ]
    return room, fixtures


def test_rcp_svg_renders_well_formed_svg() -> None:
    room, fixtures = _room_with_fixtures()
    svg = render_rcp_svg(room, fixtures)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert 'viewBox="' in svg


def test_rcp_svg_includes_each_fixture_with_layer_class() -> None:
    room, fixtures = _room_with_fixtures()
    svg = render_rcp_svg(room, fixtures)
    # one fixture per layer, glyphs drawn as <circle> with CSS class
    assert svg.count('class="fixture-ambient"') == 1
    assert svg.count('class="fixture-task"') == 1


def test_rcp_svg_includes_room_polygon() -> None:
    room, fixtures = _room_with_fixtures()
    svg = render_rcp_svg(room, fixtures)
    assert "<polygon" in svg


def test_rcp_svg_header_strip_shows_fixture_count() -> None:
    room, fixtures = _room_with_fixtures()
    svg = render_rcp_svg(room, fixtures)
    assert "2 fixtures" in svg or "2 · " in svg


def test_rcp_svg_with_no_fixtures_still_renders_polygon() -> None:
    room, _ = _room_with_fixtures()
    svg = render_rcp_svg(room, [])
    assert "<polygon" in svg
    assert "<circle" not in svg


def test_rcp_svg_handles_triangle_room() -> None:
    """Edge case: room polygon with 3 sides should render as a polygon."""
    room = Room(
        id="tri",
        name="ALCOVE",
        type=RoomType.unknown,
        floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=4, y=0), Point(x=2, y=3)],
        ceiling_height_m=2.7,
    )
    svg = render_rcp_svg(room, [])
    assert "<polygon" in svg
    assert svg.startswith("<svg")


def test_rcp_svg_handles_pentagon_room() -> None:
    """Edge case: room polygon with 5 sides should render correctly."""
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
    svg = render_rcp_svg(room, [])
    assert "<polygon" in svg
    # All 5 vertices should be present in the points attribute
    poly_open = svg.find("<polygon")
    poly_close = svg.find("/>", poly_open)
    polygon_tag = svg[poly_open:poly_close]
    assert polygon_tag.count(",") == 5  # one comma per vertex


def test_rcp_svg_unknown_cct_falls_back_to_neutral_grey() -> None:
    """Edge case: a fixture without a CCT value renders with a neutral grey fill."""
    room = Room(
        id="r",
        name="UTILITY",
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
    fixture = Fixture(
        id="u1",
        type="downlight",
        position=Point(x=1.5, y=1.5),
        layer=LightingLayer.ambient,
        cct_k=None,
    )
    svg = render_rcp_svg(room, [fixture])
    # neutral grey hex for unknown CCT
    assert "#9aa0a6" in svg


def test_rcp_svg_escapes_html_in_room_name() -> None:
    """Names containing HTML metacharacters must be escaped."""
    room = Room(
        id="r",
        name="LIVING & <FANCY>",
        type=RoomType.living,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=4, y=0),
            Point(x=4, y=3),
            Point(x=0, y=3),
        ],
        ceiling_height_m=2.7,
    )
    svg = render_rcp_svg(room, [])
    assert "&amp;" in svg
    assert "&lt;FANCY&gt;" in svg
    # raw unescaped angle-brackets from the name must not appear
    assert "<FANCY>" not in svg


def test_rcp_svg_handles_small_room_under_one_meter() -> None:
    """Edge case: a very small room must still produce a positive viewBox."""
    room = Room(
        id="tiny",
        name="CLOSET",
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
    svg = render_rcp_svg(room, [])
    assert svg.startswith("<svg")
    assert 'viewBox="0 0 ' in svg
    # No negative width/height in viewBox
    assert "viewBox=\"0 0 -" not in svg


def test_rcp_svg_handles_very_large_room() -> None:
    """Edge case: a 20m+ room must still render with finite viewBox dims."""
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
    svg = render_rcp_svg(room, [])
    assert svg.startswith("<svg")
    # width = (25 + 2) * 50 = 1350
    assert 'width="1350"' in svg
    # height = (22 + 2) * 50 = 1200
    assert 'height="1200"' in svg


def test_rcp_svg_includes_all_four_layer_classes_when_present() -> None:
    """All four LightingLayer values should map to distinct CSS classes."""
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
    fixtures = [
        Fixture(id=f"f{i}", type="x", position=Point(x=1.0 + i, y=2.0), layer=layer)
        for i, layer in enumerate(
            [
                LightingLayer.ambient,
                LightingLayer.task,
                LightingLayer.accent,
                LightingLayer.decorative,
            ]
        )
    ]
    svg = render_rcp_svg(room, fixtures)
    assert 'class="fixture-ambient"' in svg
    assert 'class="fixture-task"' in svg
    assert 'class="fixture-accent"' in svg
    assert 'class="fixture-decorative"' in svg
