"""Render the revised RCP as an SVG string.

Inputs:
  - Room (polygon, dimensions)
  - list of Fixture (placed by the multi-layer placement code)

Output: a self-contained ``<svg>`` string with:
  - viewBox sized to the room with 1m padding
  - room polygon (light fill, dark stroke)
  - fixture glyphs (color-coded by CCT, sized by layer)
  - header strip with fixture count + total wattage

The SVG embeds its own ``<style>`` block so it can be dropped into any HTML
container, embedded in a Vercel preview, or screenshotted by a designer
without external CSS or font dependencies.
"""

import html

from lighting_engine.models.geometry import Fixture, LightingLayer, Point, Room

_PX_PER_M: int = 50
_PAD_M: float = 1.0

# CCT palette — warm orange → neutral amber → cool blue. Falls back to a
# neutral grey when no CCT is supplied (parsed fixtures often lack this).
_COLOR_WARM: str = "#ff9a3c"
_COLOR_NEUTRAL: str = "#ffd07a"
_COLOR_COOL: str = "#6fc7e6"
_COLOR_UNKNOWN: str = "#9aa0a6"

# Layer glyph radii (px). Decorative fixtures read as larger, accents smaller.
_RADIUS_DEFAULT: float = 4.0
_LAYER_RADIUS: dict[LightingLayer, float] = {
    LightingLayer.ambient: 4.0,
    LightingLayer.task: 6.0,
    LightingLayer.accent: 3.5,
    LightingLayer.decorative: 9.0,
}


def _viewbox(
    polygon: list[Point],
) -> tuple[float, float, float, float, float, float]:
    """Return ``(minx, miny, width_m, height_m, svg_w_px, svg_h_px)`` with padding."""
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    minx = min(xs) - _PAD_M
    miny = min(ys) - _PAD_M
    maxx = max(xs) + _PAD_M
    maxy = max(ys) + _PAD_M
    width_m = maxx - minx
    height_m = maxy - miny
    return minx, miny, width_m, height_m, width_m * _PX_PER_M, height_m * _PX_PER_M


def _color_for_cct(cct_k: int | None) -> str:
    """Map a CCT (Kelvin) to a fill colour. Unknown CCT → neutral grey."""
    if cct_k is None:
        return _COLOR_UNKNOWN
    if cct_k <= 3000:
        return _COLOR_WARM
    if cct_k <= 3500:
        return _COLOR_NEUTRAL
    return _COLOR_COOL


def _layer_class(layer: LightingLayer) -> str:
    return f"fixture-{layer.value}"


def _radius_for_layer(layer: LightingLayer) -> float:
    return _LAYER_RADIUS.get(layer, _RADIUS_DEFAULT)


def render_rcp_svg(room: Room, fixtures: list[Fixture]) -> str:
    """Return a self-contained ``<svg>`` string for the room + placed fixtures.

    The SVG is pure-string-built (no template engine, no external assets) so
    it renders identically in any browser or HTML snapshot pipeline.
    """
    minx, miny, _width_m, _height_m, svg_w, svg_h = _viewbox(room.polygon)

    def x(v: float) -> float:
        return (v - minx) * _PX_PER_M

    def y(v: float) -> float:
        # SVG y grows downward; flip so room y grows upward as drafted.
        return svg_h - (v - miny) * _PX_PER_M

    parts: list[str] = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" '
            f'width="{svg_w:.0f}" height="{svg_h:.0f}">'
        ),
        (
            "<style>"
            ".room-poly { stroke: #2a2a2a; stroke-width: 1.5; fill: #f7f3e9;"
            " fill-opacity: 0.6; }"
            ".fixture-ambient { stroke: #6b5300; stroke-width: 0.8; }"
            ".fixture-task    { stroke: #6b5300; stroke-width: 1.2; }"
            ".fixture-accent  { stroke: #6b5300; stroke-width: 0.8;"
            " stroke-dasharray: 2 1; }"
            ".fixture-decorative { stroke: #6b5300; stroke-width: 1.4; }"
            ".header { font: 12px ui-sans-serif, system-ui; fill: #2a2a2a; }"
            "</style>"
        ),
    ]

    # Room polygon
    pts = " ".join(f"{x(p.x):.1f},{y(p.y):.1f}" for p in room.polygon)
    parts.append(f'<polygon class="room-poly" points="{pts}"/>')

    # Fixtures
    for fx in fixtures:
        cls = _layer_class(fx.layer)
        color = _color_for_cct(fx.cct_k)
        r = _radius_for_layer(fx.layer)
        cct_label = html.escape(str(fx.cct_k) if fx.cct_k is not None else "?")
        watt = fx.wattage_w if fx.wattage_w is not None else 0.0
        parts.append(
            f'<circle class="{cls}" cx="{x(fx.position.x):.1f}" '
            f'cy="{y(fx.position.y):.1f}" r="{r:.1f}" fill="{color}">'
            f"<title>{html.escape(fx.layer.value)} · "
            f"{cct_label}K · {watt:.0f}W</title>"
            "</circle>"
        )

    # Header strip
    total_w = sum((fx.wattage_w or 0.0) for fx in fixtures)
    parts.append(
        f'<text class="header" x="8" y="16">'
        f"{html.escape(room.name)} · {len(fixtures)} fixtures · {total_w:.0f}W"
        "</text>"
    )

    parts.append("</svg>")
    return "\n".join(parts)
