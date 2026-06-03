"""Render the revised furniture plan with suggested lamp positions.

The furniture SVG overlays the room polygon, the parsed furniture (small dots)
and the LLM's lamp suggestions (filled triangles + labels). It is a
self-contained ``<svg>`` string — no external CSS, no assets, no template
engine — so it renders identically in any browser, Vercel preview, or
screenshot pipeline.

**Lamp positioning fallback (v1):**

Phase 4's ``lighting.zone_interpreter.interpret_position_hint`` will eventually
resolve a Zone's free-text ``position_hint`` (e.g. "wall N near window") into a
target rectangle on the room polygon. While that interpreter is being built by
the parallel Phase 4 agent, this renderer falls back to the polygon centroid
for every lamp suggestion. The centroid is always inside (or near) the room
which is good enough for v1 furniture-plan rendering — the designer can drag
lamps in Chunk 3. When zone_interpreter lands on parser-v1, a follow-up patch
should swap ``_resolve_lamp_position`` to call the real interpreter (the
function signature is kept identical so the swap is one line).
"""

import html

from lighting_engine.brief.models import Zone
from lighting_engine.models.geometry import Point, Room

_PX_PER_M: int = 50
_PAD_M: float = 1.0

# Triangle glyph dimensions (px) — apex up, base centred on the lamp position.
_TRI_HALF_BASE_PX: float = 7.0
_TRI_HEIGHT_PX: float = 9.0
_TRI_BASE_OFFSET_PX: float = 4.0

# Lamp-archetype → CSS class. Anything unrecognised falls back to "ambient".
_LAMP_CLASS_BY_FIXTURE: dict[str, str] = {
    "floor_lamp": "lamp-floor",
    "table_lamp": "lamp-table",
}
_LAMP_CLASS_FALLBACK: str = "lamp-ambient"


def _viewbox(polygon: list[Point]) -> tuple[float, float, float, float]:
    """Return ``(minx, miny, svg_w_px, svg_h_px)`` with 1m padding."""
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    minx = min(xs) - _PAD_M
    miny = min(ys) - _PAD_M
    maxx = max(xs) + _PAD_M
    maxy = max(ys) + _PAD_M
    width_m = maxx - minx
    height_m = maxy - miny
    return minx, miny, width_m * _PX_PER_M, height_m * _PX_PER_M


def _polygon_centroid(polygon: list[Point]) -> Point:
    """Area-weighted centroid via the shoelace formula.

    Falls back to the arithmetic mean of the vertices for degenerate
    (zero-area) polygons — which shouldn't occur for a valid Room but the
    guard keeps the renderer crash-free.
    """
    n = len(polygon)
    if n == 0:
        return Point(x=0.0, y=0.0)
    a2 = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x1, y1 = polygon[i].x, polygon[i].y
        x2, y2 = polygon[(i + 1) % n].x, polygon[(i + 1) % n].y
        cross = x1 * y2 - x2 * y1
        a2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if a2 == 0.0:
        # Degenerate polygon — fall back to mean of vertices.
        mx = sum(p.x for p in polygon) / n
        my = sum(p.y for p in polygon) / n
        return Point(x=mx, y=my)
    area6 = 3.0 * a2  # 6 * signed area
    return Point(x=cx / area6, y=cy / area6)


def _resolve_lamp_position(zone: Zone, room: Room) -> Point:
    """Resolve a Zone's ``position_hint`` to a Point on the room polygon.

    v1: returns the polygon centroid as a safe fallback because the Phase-4
    ``zone_interpreter`` may not be available on the current branch. The
    signature is stable, so when the interpreter lands this function becomes
    a one-line delegation to ``interpret_position_hint``.
    """
    _ = zone  # position_hint is not yet consulted in the v1 fallback
    return _polygon_centroid(room.polygon)


def _lamp_class(fixture_type: str | None) -> str:
    """Map a Zone.fixture_type to a CSS class. Unknown → ambient fallback."""
    if not fixture_type:
        return _LAMP_CLASS_FALLBACK
    return _LAMP_CLASS_BY_FIXTURE.get(fixture_type, _LAMP_CLASS_FALLBACK)


def render_furniture_svg(room: Room, lamp_suggestions: list[Zone]) -> str:
    """Return a self-contained ``<svg>`` string for the furniture plan.

    Args:
        room: the room (polygon + parsed furniture)
        lamp_suggestions: LLM-suggested floor/table lamps (subset of the brief
            Zones — typically ``RoomBrief.floor_lamp_suggestions`` plus
            ``table_lamp_suggestions``).
    """
    minx, miny, svg_w, svg_h = _viewbox(room.polygon)

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
            ".room-poly { stroke: #2a2a2a; stroke-width: 1.5; fill: #fffbf0;"
            " fill-opacity: 0.6; }"
            ".furniture-dot { fill: #b779d4; opacity: 0.7; }"
            ".lamp-floor { fill: #ff9a3c; stroke: #8a4500; stroke-width: 0.8; }"
            ".lamp-table { fill: #ffd07a; stroke: #8a4500; stroke-width: 0.6; }"
            ".lamp-ambient { fill: #ffe1a8; stroke: #8a4500; stroke-width: 0.6;"
            " stroke-dasharray: 2 1; }"
            ".lamp-label { font: 11px ui-sans-serif, system-ui; fill: #2a2a2a; }"
            ".header { font: 12px ui-sans-serif, system-ui; fill: #2a2a2a; }"
            "</style>"
        ),
    ]

    # Room polygon
    pts = " ".join(f"{x(p.x):.1f},{y(p.y):.1f}" for p in room.polygon)
    parts.append(f'<polygon class="room-poly" points="{pts}"/>')

    # Existing furniture as small dots
    for furn in room.furniture:
        label = html.escape(furn.raw_label or furn.type or "")
        parts.append(
            f'<circle class="furniture-dot" cx="{x(furn.position.x):.1f}" '
            f'cy="{y(furn.position.y):.1f}" r="4">'
            f"<title>{label}</title></circle>"
        )

    # Lamp suggestions as triangles (apex up) with labels
    for zone in lamp_suggestions:
        target = _resolve_lamp_position(zone, room)
        cls = _lamp_class(zone.fixture_type)
        cx = x(target.x)
        cy = y(target.y)
        apex_y = cy - _TRI_HEIGHT_PX
        base_y = cy + _TRI_BASE_OFFSET_PX
        parts.append(
            f'<polygon class="{cls}" points="'
            f"{cx:.1f},{apex_y:.1f} "
            f"{cx - _TRI_HALF_BASE_PX:.1f},{base_y:.1f} "
            f'{cx + _TRI_HALF_BASE_PX:.1f},{base_y:.1f}">'
            f"<title>{html.escape(zone.purpose)}</title></polygon>"
        )
        parts.append(
            f'<text class="lamp-label" x="{cx + 10:.1f}" y="{cy + 4:.1f}">'
            f"{html.escape(zone.purpose)}</text>"
        )

    # Header strip — room name + lamp count for at-a-glance review
    parts.append(
        f'<text class="header" x="8" y="16">'
        f"{html.escape(room.name)} · {len(room.furniture)} furniture · "
        f"{len(lamp_suggestions)} lamps"
        "</text>"
    )

    parts.append("</svg>")
    return "\n".join(parts)
