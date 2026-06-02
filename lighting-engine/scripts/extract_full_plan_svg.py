"""Extract the FULL architectural plan as a single SVG.

Renders every wall LINE, every room label, every door arc, every window mark.
Adds fixture positions from the electrical file (with empirical offset applied).

Output: a single SVG string written to stdout, ready to embed in HTML.

Usage:
    cd lighting-engine
    uv run python scripts/extract_full_plan_svg.py > /tmp/full_plan.svg
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import ezdxf
from ezdxf.entities import Arc, Insert, Line, LWPolyline, MText, Text

# Empirical offset discovered by inlier-maximization search (specific to Mr. Mohak project)
ELEC_TO_ARCH_OFFSET = (1400, -700)


def strip_mtext_codes(raw: str) -> str:
    text = raw
    text = re.sub(r"\\f[^;]*?;", "", text)
    text = re.sub(r"\\p[a-zA-Z0-9.,\-\+\*\s]*?;", "", text)
    text = re.sub(r"\\H[\d\.]+x?;", "", text)
    text = re.sub(r"\\S[^;]*;", "", text)
    text = re.sub(r"\\A\d+;", "", text)
    text = re.sub(r"\\C\d+;", "", text)
    text = re.sub(r"\\[OLKolkQqWw][\d\.\-]*;?", "", text)
    text = re.sub(r"\\\\", "", text)
    text = text.replace("\\P", " | ")
    text = text.replace("{", "").replace("}", "")
    return text.strip()


def main():
    repo = Path(__file__).parent.parent
    arch_doc = ezdxf.readfile(str(repo / "tests/fixtures/dwgs/real_base_architectural.dxf"))
    elec_doc = ezdxf.readfile(str(repo / "tests/fixtures/dwgs/real_electrical_lighting.dxf"))

    msp_arch = arch_doc.modelspace()
    msp_elec = elec_doc.modelspace()

    # Determine architectural bbox from wall lines (most reliable extent)
    walls: list[tuple] = []
    for e in msp_arch.query("LINE"):
        layer = e.dxf.layer.lower()
        if "wall" in layer or "stone" in layer or "column" in layer:
            walls.append((e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y, layer))

    if not walls:
        print("No walls found", file=sys.stderr)
        sys.exit(1)

    xs = [w[0] for w in walls] + [w[2] for w in walls]
    ys = [w[1] for w in walls] + [w[3] for w in walls]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    pad = max(maxx - minx, maxy - miny) * 0.03
    minx -= pad
    maxx += pad
    miny -= pad
    maxy += pad
    svg_w = maxx - minx
    svg_h = maxy - miny

    print(f"Architectural bbox: ({minx:.0f},{miny:.0f}) to ({maxx:.0f},{maxy:.0f}) = {svg_w:.0f} x {svg_h:.0f}", file=sys.stderr)
    print(f"Walls: {len(walls)}", file=sys.stderr)

    # Windows + doors on architectural file
    windows = []
    for e in msp_arch.query("LINE"):
        if "window" in e.dxf.layer.lower():
            windows.append((e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
    print(f"Windows: {len(windows)}", file=sys.stderr)

    door_arcs = []
    for e in msp_arch.query("ARC"):
        if "door" in e.dxf.layer.lower():
            door_arcs.append((e.dxf.center.x, e.dxf.center.y, e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle))
    door_lines = []
    for e in msp_arch.query("LINE"):
        if "door" in e.dxf.layer.lower():
            door_lines.append((e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
    print(f"Door arcs: {len(door_arcs)}, door lines: {len(door_lines)}", file=sys.stderr)

    # Room labels — only keep ones with dimensions (real room labels)
    DIM_RE = re.compile(r"\d+'\s*-?\s*\d*\"?\s*[xX×]\s*\d+'?\s*-?\s*\d*\"?")
    room_labels: list[tuple[float, float, str]] = []
    for e in msp_arch.query("MTEXT TEXT"):
        try:
            if isinstance(e, MText):
                raw = e.text
                pos = e.dxf.insert
            elif isinstance(e, Text):
                raw = e.dxf.text
                pos = e.dxf.insert
            else:
                continue
            cleaned = strip_mtext_codes(raw)
            if not DIM_RE.search(cleaned):
                continue
            # Extract just the name (before the dimension)
            m = DIM_RE.search(cleaned)
            name = cleaned[: m.start()].strip(" |-").strip()
            room_labels.append((pos.x, pos.y, name))
        except Exception:
            continue
    print(f"Room labels: {len(room_labels)}", file=sys.stderr)

    # Fixtures from electrical file with offset applied
    dx_off, dy_off = ELEC_TO_ARCH_OFFSET
    fixtures = []
    for e in msp_elec.query("INSERT"):
        if "light" in e.dxf.layer.lower():
            # Transform from electrical coords → architectural coords
            x = e.dxf.insert.x - dx_off
            y = e.dxf.insert.y - dy_off
            if minx <= x <= maxx and miny <= y <= maxy:
                fixtures.append((x, y))
    print(f"Fixtures (within plan bbox after offset): {len(fixtures)}", file=sys.stderr)

    # Build SVG
    def fx(x):
        return x - minx

    def fy(y):
        return svg_h - (y - miny)

    diag = (svg_w ** 2 + svg_h ** 2) ** 0.5
    stroke_wall = diag * 0.0012
    stroke_door = diag * 0.0008
    stroke_window = diag * 0.0006
    fixture_r = diag * 0.0028
    label_size = diag * 0.006

    parts = []
    parts.append(
        f'<svg viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" xmlns="http://www.w3.org/2000/svg" '
        'class="w-full h-auto block" style="max-height: 700px; background: #1F1B16" '
        'preserveAspectRatio="xMidYMid meet">'
    )

    # Walls
    parts.append('<g id="walls">')
    for x1, y1, x2, y2, layer in walls:
        colour = "#B8B1A3" if "wall" in layer else ("#7A6B5B" if "column" in layer else "#A89888")
        parts.append(
            f'<line x1="{fx(x1):.1f}" y1="{fy(y1):.1f}" x2="{fx(x2):.1f}" y2="{fy(y2):.1f}" '
            f'stroke="{colour}" stroke-width="{stroke_wall:.2f}" stroke-linecap="round"/>'
        )
    parts.append("</g>")

    # Windows
    parts.append('<g id="windows" stroke="#7090B0" stroke-dasharray="4 3">')
    for x1, y1, x2, y2 in windows:
        parts.append(
            f'<line x1="{fx(x1):.1f}" y1="{fy(y1):.1f}" x2="{fx(x2):.1f}" y2="{fy(y2):.1f}" '
            f'stroke-width="{stroke_window:.2f}"/>'
        )
    parts.append("</g>")

    # Door arcs (a door is typically a quarter-circle showing swing direction)
    import math
    parts.append('<g id="doors" stroke="#A89888" fill="none">')
    for cx, cy, r, a0, a1 in door_arcs:
        # Convert polar to cartesian, build a path
        a0r = math.radians(a0)
        a1r = math.radians(a1)
        x0 = cx + r * math.cos(a0r)
        y0 = cy + r * math.sin(a0r)
        x1 = cx + r * math.cos(a1r)
        y1 = cy + r * math.sin(a1r)
        # SVG arc flag: large_arc=0 for <180°, sweep=1 for counterclockwise (Y is flipped)
        large = 1 if (a1 - a0) % 360 > 180 else 0
        # Y axis flip → swap sweep
        parts.append(
            f'<path d="M {fx(x0):.1f} {fy(y0):.1f} A {r:.1f} {r:.1f} 0 {large} 0 {fx(x1):.1f} {fy(y1):.1f}" '
            f'stroke-width="{stroke_door:.2f}"/>'
        )
    parts.append("</g>")

    # Fixtures
    parts.append('<g id="fixtures">')
    for x, y in fixtures:
        parts.append(
            f'<circle cx="{fx(x):.1f}" cy="{fy(y):.1f}" r="{fixture_r:.1f}" '
            'fill="#FBBF77" opacity="0.85"/>'
        )
    parts.append("</g>")

    # Room labels — highlight the 4 audited rooms
    AUDITED = {"MASTER BEDROOM", "LOBBY", "MASTER TOILET", "STUDY ROOM"}
    parts.append(
        f'<g id="labels" font-family="Inter, sans-serif" font-size="{label_size:.1f}" '
        'text-anchor="middle">'
    )
    for x, y, name in room_labels:
        is_audited = name.upper() in AUDITED
        fill = "#FBBF77" if is_audited else "rgba(255,255,255,0.55)"
        weight = "600" if is_audited else "400"
        # Background pill for audited rooms
        if is_audited:
            text_w = len(name) * label_size * 0.55
            parts.append(
                f'<rect x="{fx(x) - text_w/2 - label_size*0.3:.1f}" '
                f'y="{fy(y) - label_size*0.8:.1f}" '
                f'width="{text_w + label_size*0.6:.1f}" '
                f'height="{label_size*1.4:.1f}" '
                f'rx="{label_size*0.4:.1f}" fill="rgba(180,83,9,0.85)"/>'
            )
            fill = "white"
        parts.append(
            f'<text x="{fx(x):.1f}" y="{fy(y) + label_size*0.35:.1f}" '
            f'fill="{fill}" font-weight="{weight}">{name}</text>'
        )
    parts.append("</g>")

    parts.append("</svg>")

    print("\n".join(parts))


if __name__ == "__main__":
    main()
