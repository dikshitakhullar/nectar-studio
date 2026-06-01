"""Visualize a parsed Project IR as an SVG overlaid on the source drawing.

Renders walls (gray), room polygons (translucent fill + outline), room names
at centroids, doors and windows on their walls, furniture as small dots with
raw_label tooltips, and existing fixtures as larger dots. The SVG uses the
Project's local-meter coordinate frame; the DXF walls are converted to the
same frame for overlay.

Usage:
    uv run python scripts/visualize_parse.py FILE.dxf [--out PATH]
"""

import argparse
import html
from pathlib import Path

from lighting_engine.models.geometry import Project
from lighting_engine.parser.geometry import find_plan_region
from lighting_engine.parser.layers import LayerRole, classify_layers
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.pipeline import parse_file

INCH_TO_M = 0.0254
_PALETTE = [
    "#4C9EEB", "#E48F4A", "#5FBE6E", "#B779D4",
    "#E2C547", "#E26A6A", "#7BC2C7", "#A88E58",
]


def _local_boundary_segments(
    dxf_path: Path,
) -> tuple[
    list[tuple[tuple[float, float], tuple[float, float]]],
    list[tuple[tuple[float, float], tuple[float, float]]],
]:
    """Return (walls, windows) as segment lists in the local-meter frame.

    Windows are pulled from the `window` / `GLASS` layers so the visualiser
    can show where actual glazing is in the source drawing — a debugging aid
    to verify the window-as-boundary signal is finding the right openings.
    """
    load = load_drawing(dxf_path)
    doc = load.document
    msp = doc.modelspace()
    layer_roles = classify_layers([layer.dxf.name for layer in doc.layers])
    wall_layers = set(layer_roles.get(LayerRole.wall, []))
    window_layers = set(layer_roles.get(LayerRole.window, []))

    walls_raw: list[tuple[tuple[float, float], tuple[float, float]]] = []
    wins_raw: list[tuple[tuple[float, float], tuple[float, float]]] = []

    for e in msp.query("LINE"):
        seg = (
            (float(e.dxf.start.x), float(e.dxf.start.y)),
            (float(e.dxf.end.x), float(e.dxf.end.y)),
        )
        if e.dxf.layer in wall_layers:
            walls_raw.append(seg)
        elif e.dxf.layer in window_layers:
            wins_raw.append(seg)

    # Many windows are drawn as closed LWPolyline frames, not loose lines —
    # decompose their edges so the visualiser shows them.
    for e in msp.query("LWPOLYLINE"):
        target = (
            walls_raw if e.dxf.layer in wall_layers
            else wins_raw if e.dxf.layer in window_layers
            else None
        )
        if target is None:
            continue
        verts = [(float(v[0]), float(v[1])) for v in e.get_points()]
        for i in range(len(verts) - 1):
            target.append((verts[i], verts[i + 1]))
        if getattr(e, "closed", False) and len(verts) >= 3:
            target.append((verts[-1], verts[0]))

    centroids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in walls_raw]
    if not centroids:
        return [], []
    region = find_plan_region(centroids)

    def to_local(segs: list[tuple[tuple[float, float], tuple[float, float]]]) -> list[
        tuple[tuple[float, float], tuple[float, float]]
    ]:
        return [
            (
                ((a[0] - region.min_x) * INCH_TO_M, (a[1] - region.min_y) * INCH_TO_M),
                ((b[0] - region.min_x) * INCH_TO_M, (b[1] - region.min_y) * INCH_TO_M),
            )
            for a, b in segs
            if region.contains(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        ]

    return to_local(walls_raw), to_local(wins_raw)




def _bounds(
    walls: list[tuple[tuple[float, float], tuple[float, float]]],
    project: Project,
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for a, b in walls:
        xs.extend([a[0], b[0]])
        ys.extend([a[1], b[1]])
    for r in project.rooms:
        for p in r.polygon:
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        return 0.0, 0.0, 10.0, 10.0
    pad = 0.5  # meters
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def render_svg(*, project: Project, dxf_path: Path, output_path: Path) -> None:
    walls, windows = _local_boundary_segments(dxf_path)
    minx, miny, maxx, maxy = _bounds(walls, project)
    width = maxx - minx
    height = maxy - miny
    px_per_m = 50
    svg_w = width * px_per_m
    svg_h = height * px_per_m

    def x(v: float) -> float:
        return (v - minx) * px_per_m

    def y(v: float) -> float:
        return svg_h - (v - miny) * px_per_m

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" '
        f'width="{svg_w:.0f}" height="{svg_h:.0f}">',
        "<style>"
        ".wall-line { stroke: #6b6b6b; stroke-width: 1.2; }"
        ".window-line { stroke: #2c8fd4; stroke-width: 2.2; }"
        ".room-poly { stroke: #2a2a2a; stroke-width: 1.5; fill-opacity: 0.18; }"
        ".room-label { font: 11px ui-sans-serif, system-ui; fill: #1a1a1a; "
        "text-anchor: middle; }"
        ".fixture-dot { fill: #f0c419; stroke: #6b5300; stroke-width: 0.8; }"
        ".furniture-dot { fill: #b779d4; opacity: 0.7; }"
        "</style>",
    ]

    # Walls
    parts.append('<g class="walls">')
    for a, b in walls:
        parts.append(
            f'<line class="wall-line" x1="{x(a[0]):.1f}" y1="{y(a[1]):.1f}" '
            f'x2="{x(b[0]):.1f}" y2="{y(b[1]):.1f}"/>'
        )
    parts.append("</g>")

    # Windows (window/GLASS layer) — drawn in blue so you can see the glazing
    parts.append('<g class="windows">')
    for a, b in windows:
        parts.append(
            f'<line class="window-line" x1="{x(a[0]):.1f}" y1="{y(a[1]):.1f}" '
            f'x2="{x(b[0]):.1f}" y2="{y(b[1]):.1f}"/>'
        )
    parts.append("</g>")

    # Rooms — polygons + name labels
    parts.append('<g class="rooms">')
    for i, room in enumerate(project.rooms):
        colour = _PALETTE[i % len(_PALETTE)]
        pts = " ".join(f"{x(p.x):.1f},{y(p.y):.1f}" for p in room.polygon)
        parts.append(
            f'<polygon class="room-poly" points="{pts}" fill="{colour}"/>'
        )
        cx = sum(p.x for p in room.polygon) / len(room.polygon)
        cy = sum(p.y for p in room.polygon) / len(room.polygon)
        label = room.name
        if room.floor_level != 0:
            label += f" (floor {room.floor_level})"
        parts.append(
            f'<text class="room-label" x="{x(cx):.1f}" y="{y(cy):.1f}">'
            f"{html.escape(label)}</text>"
        )
    parts.append("</g>")

    # Furniture
    parts.append('<g class="furniture">')
    for room in project.rooms:
        for f in room.furniture:
            label = html.escape(f.raw_label or "")
            parts.append(
                f'<circle class="furniture-dot" cx="{x(f.position.x):.1f}" '
                f'cy="{y(f.position.y):.1f}" r="3"><title>{label}</title></circle>'
            )
    parts.append("</g>")

    # Existing fixtures
    parts.append('<g class="fixtures">')
    for room in project.rooms:
        for fx in room.existing_fixtures:
            label = html.escape(fx.raw_label or "")
            parts.append(
                f'<circle class="fixture-dot" cx="{x(fx.position.x):.1f}" '
                f'cy="{y(fx.position.y):.1f}" r="5"><title>{label}</title></circle>'
            )
    parts.append("</g>")

    parts.append("</svg>")
    output_path.write_text("\n".join(parts))


def main() -> None:
    p = argparse.ArgumentParser(description="Render a parsed Project as SVG")
    p.add_argument("dxf", type=Path, help="Path to a .dwg or .dxf file")
    p.add_argument(
        "--out", type=Path, default=None,
        help="Output SVG path (default: /tmp/<filename>.svg)",
    )
    args = p.parse_args()
    project, _ = parse_file(args.dxf, project_name=args.dxf.stem)
    out = args.out or Path("/tmp") / f"{args.dxf.stem}.svg"
    render_svg(project=project, dxf_path=args.dxf, output_path=out)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
