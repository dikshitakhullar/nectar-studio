"""Extract real per-room SVG layouts from architectural + electrical DXF files.

Heuristic approach (until proper room polygon detection ships):
  - Find each room label (MTEXT) by name match
  - Parse its declared dimensions (e.g. "18'-4½" x 24'-3"")
  - Build a bounding box around the label, sized to declared dimensions + padding
  - Crop wall LINEs and fixture INSERTs that fall inside the bbox
  - Emit SVG per room

Usage:
    cd lighting-engine
    uv run python scripts/extract_room_svgs.py > /tmp/room_svgs.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import ezdxf
from ezdxf.entities import Insert, Line, MText, Text

# Rooms we want — substring of label name → HTML id used in the mockup
ROOM_TARGETS: list[tuple[str, str]] = [
    ("MASTER BEDROOM", "master-bedroom"),
    ("LOBBY", "lobby"),
    ("MASTER TOILET", "master-toilet"),
    ("STUDY ROOM", "study"),
]

# Padding around the labeled room rectangle so we capture surrounding walls
PADDING_FACTOR = 0.25  # 25 % of the room dimension as padding on each side

# Fixture-capture padding is wider — the architect's label is at room center but
# the electrical drawing places downlights at the room perimeter
FIXTURE_PADDING_FACTOR = 1.5

# Stroke widths in DXF units (will scale with viewBox)
WALL_STROKE_FACTOR = 0.012  # fraction of viewBox diagonal

# Empirically-discovered offset between the architectural and electrical coordinate
# frames for this specific project (Mr. Mohak's residence). Replaces the rigorous
# wall-corner-matching algorithm that ships in v1's Phase 3 parser amendment.
# To find: brute-force grid search of dx, dy that maximises fixture-in-room inliers.
ELEC_TO_ARCH_OFFSET = (1400, -700)  # apply to ARCH coords to reach ELEC coords


def strip_mtext_codes(raw: str) -> str:
    """Strip AutoCAD MText control codes to get raw text."""
    text = raw
    # \fFontName|b0|i0|c0|p34;
    text = re.sub(r"\\f[^;]*?;", "", text)
    # \pxqc; \pl1.5,t1.5; — paragraph properties (must allow letters in body)
    text = re.sub(r"\\p[a-zA-Z0-9.,\-\+\*\s]*?;", "", text)
    # \H0.7x; \H12;
    text = re.sub(r"\\H[\d\.]+x?;", "", text)
    # \S1#2; \S1/2; \S1^2;  (stacked fraction)
    text = re.sub(r"\\S[^;]*;", "", text)
    # \A0; \A1; \A2;  (alignment)
    text = re.sub(r"\\A\d+;", "", text)
    # \C123; (colour)
    text = re.sub(r"\\C\d+;", "", text)
    # \O ... \o (over), \L ... \l (under), \K ... \k (strike), \Q angle, \W width
    text = re.sub(r"\\[OLKolkQqWw][\d\.\-]*;?", "", text)
    # escaped braces / backslash
    text = re.sub(r"\\\\", "", text)
    # \P = MText newline
    text = text.replace("\\P", " ")
    # leftover braces
    text = text.replace("{", "").replace("}", "")
    return text.strip()


# Match: 18'-4" x 24'-3"   OR   29'-3"x11'-9"  OR  22'-0"X16'-9"
_DIM_RE = re.compile(
    r"(\d+)'\s*-?\s*(\d*)\"?\s*[xX×]\s*(\d+)'?\s*-?\s*(\d*)\"?"
)


def parse_label_dims(text: str) -> tuple[str, float | None, float | None]:
    """Parse label text into (name, width_in, height_in).
    Real labels look like 'MASTER BEDROOM 18'-4" x 24'-3"' (after stripping MText codes).
    """
    cleaned = strip_mtext_codes(text)
    # Find dimensions anywhere in the cleaned text
    m = _DIM_RE.search(cleaned)
    width_in = height_in = None
    name_part = cleaned
    if m:
        ft1, in1, ft2, in2 = m.groups()
        width_in = int(ft1) * 12 + (int(in1) if in1 else 0)
        height_in = int(ft2) * 12 + (int(in2) if in2 else 0)
        # Name = everything before the first digit / quote pattern
        name_part = cleaned[: m.start()]
    # Trim trailing punctuation/whitespace/pipes from name
    name = re.sub(r"[\|\s\-]+$", "", name_part).strip().upper()
    return name, width_in, height_in


def find_room_labels(doc) -> dict[str, dict]:
    """Returns {html_id: {label_x, label_y, width_in, height_in, full_text}} for matching rooms."""
    msp = doc.modelspace()
    found: dict[str, dict] = {}
    candidates: list[tuple[str, float, float, float, float]] = []

    for e in msp.query("MTEXT TEXT"):
        try:
            if isinstance(e, MText):
                raw = e.text
                pos = e.dxf.insert
            elif isinstance(e, Text):
                raw = e.dxf.text
                pos = e.dxf.insert
            else:
                continue
            name, w, h = parse_label_dims(raw)
            if w and h:
                candidates.append((name, pos.x, pos.y, w, h))
        except Exception:
            continue

    for substr, html_id in ROOM_TARGETS:
        # Prefer most specific match (longest substring overlap) and skip already-claimed positions
        for name, x, y, w, h in candidates:
            if substr in name and html_id not in found:
                # Avoid false positive: e.g. don't let "STUDY" claim a label that also contains another keyword we want
                already_claimed_substrings = [s for s, hid in ROOM_TARGETS if hid in found]
                if any(other in name for other in already_claimed_substrings if other != substr):
                    continue
                found[html_id] = dict(
                    label_x=x, label_y=y, width_in=w, height_in=h, full_text=name
                )
                break
    return found


def lines_in_bbox(doc, bbox: tuple[float, float, float, float], layer_substr: str = "wall") -> list[tuple]:
    """Yield LINE entities that intersect the bbox (any endpoint inside)."""
    minx, miny, maxx, maxy = bbox
    msp = doc.modelspace()
    out = []
    for e in msp.query("LINE"):
        layer = e.dxf.layer.lower()
        if layer_substr not in layer:
            continue
        x1, y1 = e.dxf.start.x, e.dxf.start.y
        x2, y2 = e.dxf.end.x, e.dxf.end.y
        # Keep if either endpoint inside bbox
        if (minx <= x1 <= maxx and miny <= y1 <= maxy) or (
            minx <= x2 <= maxx and miny <= y2 <= maxy
        ):
            out.append((x1, y1, x2, y2))
    return out


def inserts_in_bbox(doc, bbox, layer_substrs: tuple[str, ...] = ("light",)) -> list[tuple]:
    """Yield INSERT (block reference) entities in bbox."""
    minx, miny, maxx, maxy = bbox
    msp = doc.modelspace()
    out = []
    for e in msp.query("INSERT"):
        layer = e.dxf.layer.lower()
        if not any(s in layer for s in layer_substrs):
            continue
        x, y = e.dxf.insert.x, e.dxf.insert.y
        if minx <= x <= maxx and miny <= y <= maxy:
            out.append((x, y, e.dxf.name, e.dxf.layer))
    return out


def build_svg(
    *,
    label_info: dict,
    walls: list[tuple],
    fixtures: list[tuple],
    pad_factor: float = PADDING_FACTOR,
) -> str:
    """Construct an SVG string. DXF Y axis is flipped for SVG."""
    label_x = label_info["label_x"]
    label_y = label_info["label_y"]
    w_in = label_info["width_in"]
    h_in = label_info["height_in"]

    pad_x = w_in * pad_factor
    pad_y = h_in * pad_factor

    minx = label_x - w_in / 2 - pad_x
    maxx = label_x + w_in / 2 + pad_x
    miny = label_y - h_in / 2 - pad_y
    maxy = label_y + h_in / 2 + pad_y
    svg_w = maxx - minx
    svg_h = maxy - miny

    # Stroke width relative to drawing scale
    stroke = max(1.0, ((svg_w + svg_h) / 2) * WALL_STROKE_FACTOR)

    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" '
        'class="w-full h-auto" style="max-height: 360px" '
        'preserveAspectRatio="xMidYMid meet">'
    )

    # Background room rect (subtle outline of the labeled region)
    rx = pad_x
    ry = pad_y
    rw = w_in
    rh = h_in
    parts.append(
        f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" '
        'fill="none" stroke="rgba(255,255,255,0.10)" stroke-dasharray="6 4" '
        f'stroke-width="{stroke * 0.5:.2f}"/>'
    )

    # Walls — use class for CSS-driven scene-aware colour
    parts.append('<g class="walls">')
    for x1, y1, x2, y2 in walls:
        sx1 = x1 - minx
        sy1 = svg_h - (y1 - miny)
        sx2 = x2 - minx
        sy2 = svg_h - (y2 - miny)
        parts.append(
            f'<line x1="{sx1:.1f}" y1="{sy1:.1f}" x2="{sx2:.1f}" y2="{sy2:.1f}" '
            f'class="wall-line" style="stroke-width: {stroke:.2f}"/>'
        )
    parts.append("</g>")

    # Existing fixtures from electrical layer
    parts.append('<g class="existing-fixtures">')
    radius = max(4, stroke * 1.5)
    for x, y, name, layer in fixtures:
        sx = x - minx
        sy = svg_h - (y - miny)
        spec = f'{{"label":"Existing fixture ({name})","type":"From electrical DWG","watts":"unknown — needs batch tag","cct":"unknown"}}'
        parts.append(
            f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{radius:.1f}" class="light dl-existing" '
            f"data-fixture='{spec}'/>"
        )
    parts.append("</g>")

    # Proposed group reserved (the JS view toggle still works; populate later)
    parts.append('<g class="proposed-fixtures" style="display: none"></g>')

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    repo = Path(__file__).parent.parent
    arch_path = repo / "tests/fixtures/dwgs/real_base_architectural.dxf"
    elec_path = repo / "tests/fixtures/dwgs/real_electrical_lighting.dxf"

    arch_doc = ezdxf.readfile(str(arch_path))
    elec_doc = ezdxf.readfile(str(elec_path))

    labels = find_room_labels(arch_doc)
    print(f"Labels matched: {list(labels.keys())}", file=sys.stderr)
    for hid, info in labels.items():
        print(
            f"  {hid}: '{info['full_text']}' at "
            f"({info['label_x']:.1f}, {info['label_y']:.1f}) "
            f"dims {info['width_in']}\" x {info['height_in']}\"",
            file=sys.stderr,
        )

    output = {}
    dx_off, dy_off = ELEC_TO_ARCH_OFFSET
    for html_id, info in labels.items():
        pad_x = info["width_in"] * PADDING_FACTOR
        pad_y = info["height_in"] * PADDING_FACTOR
        wall_bbox = (
            info["label_x"] - info["width_in"] / 2 - pad_x,
            info["label_y"] - info["height_in"] / 2 - pad_y,
            info["label_x"] + info["width_in"] / 2 + pad_x,
            info["label_y"] + info["height_in"] / 2 + pad_y,
        )

        # Fixture bbox is in ELECTRICAL coords — apply offset
        fix_pad_x = info["width_in"] * FIXTURE_PADDING_FACTOR
        fix_pad_y = info["height_in"] * FIXTURE_PADDING_FACTOR
        elec_cx = info["label_x"] + dx_off
        elec_cy = info["label_y"] + dy_off
        fixture_bbox = (
            elec_cx - info["width_in"] / 2 - fix_pad_x,
            elec_cy - info["height_in"] / 2 - fix_pad_y,
            elec_cx + info["width_in"] / 2 + fix_pad_x,
            elec_cy + info["height_in"] / 2 + fix_pad_y,
        )

        walls = lines_in_bbox(arch_doc, wall_bbox, layer_substr="wall")
        fixtures_elec = inserts_in_bbox(elec_doc, fixture_bbox, layer_substrs=("light",))
        # Translate fixture positions back into architectural coords for rendering
        fixtures = [(x - dx_off, y - dy_off, name, layer) for x, y, name, layer in fixtures_elec]

        print(
            f"  {html_id}: {len(walls)} wall lines, {len(fixtures)} fixtures (offset-aligned)",
            file=sys.stderr,
        )
        svg = build_svg(label_info=info, walls=walls, fixtures=fixtures)
        output[html_id] = {
            "svg": svg,
            "wall_count": len(walls),
            "fixture_count": len(fixtures),
            "label_text": info["full_text"],
            "dims_ft": (info["width_in"] / 12, info["height_in"] / 12),
        }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
