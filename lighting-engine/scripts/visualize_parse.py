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

from ezdxf.entities.lwpolyline import LWPolyline

from lighting_engine.models.geometry import Project
from lighting_engine.parser.geometry import find_plan_region
from lighting_engine.parser.layers import LayerRole, classify_layers
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.pipeline import parse_file
from lighting_engine.parser.window_filter import filter_valid_windows

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
        if not isinstance(e, LWPolyline):
            continue
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
        if e.closed and len(verts) >= 3:
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
    walls, raw_windows = _local_boundary_segments(dxf_path)
    # Apply the same "must be on an interior room wall" filter the pipeline
    # uses, so the SVG shows only the windows that survive — phantom window-
    # layer linework on terraces / courtyards / staircases is excluded.
    windows, dropped_windows = filter_valid_windows(raw_windows, project.rooms)
    print(
        f"Window segments: kept {len(windows)} / dropped "
        f"{len(dropped_windows)} (of {len(raw_windows)} raw on window/GLASS layers)"
    )
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
        # Diagonal-stripe pattern used to mark double-height (open-to-below)
        # regions over their host room polygon.
        '<defs>'
        '<pattern id="double-height-stripes" patternUnits="userSpaceOnUse" '
        'width="8" height="8" patternTransform="rotate(45)">'
        '<rect width="8" height="8" fill="#d94f4f" fill-opacity="0.10"/>'
        '<line x1="0" y1="0" x2="0" y2="8" stroke="#d94f4f" '
        'stroke-width="1.5" stroke-opacity="0.55"/>'
        '</pattern>'
        '</defs>',
        "<style>"
        ".wall-line { stroke: #6b6b6b; stroke-width: 1.2; }"
        ".window-line { stroke: #1f7ad6; stroke-width: 4.0; stroke-linecap: round; }"
        ".room-poly { stroke: #2a2a2a; stroke-width: 1.5; fill-opacity: 0.18; }"
        ".room-label { font: 11px ui-sans-serif, system-ui; fill: #1a1a1a; "
        "text-anchor: middle; }"
        ".fixture-dot { fill: #f0c419; stroke: #6b5300; stroke-width: 0.8; }"
        ".proposed-warm { fill: #ff9a3c; stroke: #8a4500; stroke-width: 0.8; }"
        ".proposed-cool { fill: #6fc7e6; stroke: #2c5f72; stroke-width: 0.8; }"
        ".furniture-dot { fill: #b779d4; opacity: 0.7; }"
        ".double-height-poly { fill: url(#double-height-stripes); "
        "stroke: #d94f4f; stroke-width: 1.0; stroke-dasharray: 4,3; }"
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

    # Double-height (open-to-below) regions — drawn AFTER rooms so the
    # diagonal-stripe overlay sits visibly on top of the room fill, but
    # BEFORE windows / furniture / fixtures so those stay legible.
    parts.append('<g class="double-height">')
    for room in project.rooms:
        for dh_poly in room.double_height_polygons:
            pts = " ".join(f"{x(p.x):.1f},{y(p.y):.1f}" for p in dh_poly)
            parts.append(
                f'<polygon class="double-height-poly" points="{pts}">'
                f"<title>double-height ({html.escape(room.name)})</title>"
                "</polygon>"
            )
    parts.append("</g>")

    # Windows (window/GLASS layer) — drawn AFTER rooms so they stay visible
    # on top of the translucent room polygons.
    parts.append('<g class="windows">')
    for a, b in windows:
        parts.append(
            f'<line class="window-line" x1="{x(a[0]):.1f}" y1="{y(a[1]):.1f}" '
            f'x2="{x(b[0]):.1f}" y2="{y(b[1]):.1f}"/>'
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

    # Fixtures — render proposed (engine output) and parsed (architect's) as
    # different colours/sizes. Proposed warm = orange, cool = light blue.
    from lighting_engine.models.geometry import FixtureSource
    parts.append('<g class="fixtures">')
    for room in project.rooms:
        for fx in room.existing_fixtures:
            label = html.escape(
                fx.raw_label or f"{fx.source.value} ({fx.cct_k or '?'}K)"
            )
            if fx.source == FixtureSource.proposed:
                css_class = "proposed-cool" if (fx.cct_k or 0) >= 3500 else "proposed-warm"
                radius = 4
            else:
                css_class = "fixture-dot"
                radius = 5
            parts.append(
                f'<circle class="{css_class}" cx="{x(fx.position.x):.1f}" '
                f'cy="{y(fx.position.y):.1f}" r="{radius}">'
                f'<title>{label}</title></circle>'
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
    p.add_argument(
        "--place", action="store_true",
        help="Also compute and render proposed ambient downlights",
    )
    args = p.parse_args()
    project, _ = parse_file(args.dxf, project_name=args.dxf.stem)

    # Diagnostic: report which rooms were tagged as having double-height regions
    # and how many polygons were attached. Useful for verifying the dotted-line
    # detector on a new fixture without opening the SVG.
    dh_total = sum(len(r.double_height_polygons) for r in project.rooms)
    dh_rooms = [
        (r.name, len(r.double_height_polygons))
        for r in project.rooms
        if r.double_height_polygons
    ]
    print(f"Double-height polygons attached: {dh_total} across {len(dh_rooms)} room(s)")
    for name, count in dh_rooms:
        suffix = "" if count == 1 else f" ({count} polygons)"
        print(f"  - {name}{suffix}")

    if args.place:
        from lighting_engine.digest import compute_digest
        from lighting_engine.lighting import compute_ambient_layer
        digest = compute_digest(project)
        digest_by_id = {d.room_id: d for d in digest.rooms}
        proposed_count = 0
        for room in project.rooms:
            d = digest_by_id.get(room.id)
            if d is None:
                continue
            for f in compute_ambient_layer(room, d):
                room.existing_fixtures.append(f)
                proposed_count += 1
        print(f"Placed {proposed_count} proposed ambient fixtures.")

    out = args.out or Path("/tmp") / f"{args.dxf.stem}.svg"
    render_svg(project=project, dxf_path=args.dxf, output_path=out)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
