"""Inject real-data per-room SVGs into the mock HTML.

Reads:
  - /tmp/room_svgs.json   (output of extract_room_svgs.py)
  - docs/mockups/sample-lighting-audit.html  (the existing mock HTML)

Writes:
  - docs/mockups/sample-lighting-audit-real.html  (new HTML with real SVGs swapped in)

The HTML has a section per room with this shape:

    <div class="room-svg-wrap p-4" data-svg="<room-id>">
      <svg ...>...stylized...</svg>
    </div>

We swap the entire inner <svg>...</svg> with the extracted real-data SVG, preserving
the wrapper div (so scene-toggle classes, padding, etc. still apply).

The fixture interactivity (proposed pendants, sconces, wall washers from the stylized SVG)
is lost on swap — we don't yet have real proposed-fixture positions. The "Proposed"
view-toggle button still works but shows no new fixtures.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main():
    repo = Path(__file__).parent.parent.parent
    html_path = repo / "docs/mockups/sample-lighting-audit.html"
    json_path = Path("/tmp/room_svgs.json")
    out_path = repo / "docs/mockups/sample-lighting-audit-real.html"

    if not html_path.exists():
        print(f"ERROR: HTML not found at {html_path}", file=sys.stderr)
        sys.exit(1)
    if not json_path.exists():
        print(
            f"ERROR: JSON not found at {json_path}. Run extract_room_svgs.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    html = html_path.read_text()
    svgs = json.loads(json_path.read_text())

    for room_id, info in svgs.items():
        # Match: <div class="room-svg-wrap p-4" data-svg="<room_id>">  ...  </div>
        # The first </svg> inside is what we want to replace up to.
        # Allow HTML comments + whitespace between the wrapper div and the <svg>
        pattern = re.compile(
            r'(<div class="room-svg-wrap p-4" data-svg="' + re.escape(room_id) + r'">)'
            r"(?:\s*<!--[\s\S]*?-->)*"
            r"\s*(<svg[\s\S]*?</svg>)",
            re.MULTILINE,
        )
        m = pattern.search(html)
        if not m:
            print(f"WARN: room {room_id} not found in HTML", file=sys.stderr)
            continue

        replacement = m.group(1) + "\n        " + info["svg"]
        html = pattern.sub(lambda mo: replacement, html, count=1)
        print(
            f"  injected {room_id}: {info['wall_count']} walls "
            f"(dims {info['dims_ft'][0]:.1f}'×{info['dims_ft'][1]:.1f}')",
            file=sys.stderr,
        )

    # Update the page title to mark this as the real-data version
    html = html.replace(
        "<title>Lighting Audit — Proposed Residence at Mandi for Mr. Mohak</title>",
        "<title>Lighting Audit — Real Cut-outs · Mr. Mohak Residence</title>",
    )
    html = html.replace(
        '<div class="serif text-lg font-light" style="color: var(--ink)">Lighting Audit</div>',
        '<div class="serif text-lg font-light" style="color: var(--ink)">Lighting Audit <span class="text-xs uppercase tracking-wider align-middle ml-2 px-2 py-0.5 rounded" style="background: var(--amber-soft); color: var(--amber)">Real cut-outs</span></div>',
    )

    out_path.write_text(html)
    print(f"\nwrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
