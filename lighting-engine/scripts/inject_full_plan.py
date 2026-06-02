"""Inject the full-plan SVG into the stylized audit HTML.

Reads:
  - docs/mockups/sample-lighting-audit.html  (stylized version, clean)
  - /tmp/full_plan.svg                       (full architectural plan)

Writes:
  - docs/mockups/sample-lighting-audit-real.html  (stylized + real plan hero at top)

We DO NOT touch the per-room cards. The cutout approach was inaccurate; we revert to
stylized SVGs (already in the stylized HTML) and add a separate "real plan" hero section.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Insert the plan section right before "</section>" of the first overview block.
# Actually we insert it RIGHT AFTER the overview section closes, before methodology.

PLAN_SECTION_TEMPLATE = """
<!-- ============ REAL FLOOR PLAN (from architectural DXF) ============ -->
<section id="floor-plan" class="bg-white rounded-lg shadow-sm overflow-hidden" style="border: 1px solid var(--rule)">
  <header class="p-6 pb-4" style="border-bottom: 1px solid var(--rule)">
    <div class="flex items-start justify-between flex-wrap gap-3">
      <div>
        <div class="text-xs uppercase tracking-wider mb-1" style="color: var(--amber)">Parsed from BASE FILE.dxf · 2,457 walls · 84 labelled rooms</div>
        <h2 class="serif text-2xl font-light">The villa, as drawn</h2>
        <p class="text-xs mt-1" style="color: var(--ink-muted)">Auto-extracted from the architectural DXF. Highlighted rooms are the four audited in this pack. Yellow dots are existing lighting fixtures from the electrical layout (offset-aligned).</p>
      </div>
      <div class="text-xs px-3 py-1.5 rounded" style="background: var(--amber-soft); color: var(--amber)">Live parse · v0</div>
    </div>
  </header>
  <div class="p-4" style="background: #1F1B16">
    __PLAN_SVG__
  </div>
  <div class="px-6 py-3 text-xs flex items-center justify-between flex-wrap gap-3" style="color: var(--ink-muted)">
    <div class="flex items-center gap-4">
      <span class="flex items-center gap-1.5"><span style="display:inline-block; width:14px; height:2px; background:#B8B1A3;"></span> Walls</span>
      <span class="flex items-center gap-1.5"><span style="display:inline-block; width:14px; height:2px; background:#7090B0; border-top: 1px dashed transparent;"></span> Windows</span>
      <span class="flex items-center gap-1.5"><span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#FBBF77;"></span> Existing fixtures (offset-aligned)</span>
      <span class="flex items-center gap-1.5"><span style="display:inline-block; padding: 1px 6px; background: rgba(180,83,9,0.85); color: white; border-radius: 3px; font-size: 9px;">AUDITED</span> 4 rooms in this pack</span>
    </div>
    <span class="italic">Per-room layout cut-outs (with stitched polygons + per-room fixture extraction) ship with v1's Phase 3 parser amendment.</span>
  </div>
</section>
"""


def main():
    repo = Path(__file__).parent.parent.parent
    src_html = repo / "docs/mockups/sample-lighting-audit.html"
    plan_svg_path = Path("/tmp/full_plan.svg")
    out_html = repo / "docs/mockups/sample-lighting-audit-real.html"

    if not src_html.exists():
        print(f"ERROR: stylized HTML not found at {src_html}", file=sys.stderr)
        sys.exit(1)
    if not plan_svg_path.exists():
        print(f"ERROR: plan SVG not found at {plan_svg_path}. Run extract_full_plan_svg.py first.", file=sys.stderr)
        sys.exit(1)

    html = src_html.read_text()
    plan_svg = plan_svg_path.read_text()

    plan_section = PLAN_SECTION_TEMPLATE.replace("__PLAN_SVG__", plan_svg)

    # Find the methodology section, insert before it
    marker = '<!-- METHODOLOGY -->'
    if marker not in html:
        print(f"ERROR: marker {marker!r} not found in HTML", file=sys.stderr)
        sys.exit(1)
    html = html.replace(marker, plan_section + "\n\n" + marker)

    # Update the title + header badge to mark this as the "real plan" version
    html = html.replace(
        "<title>Lighting Audit — Proposed Residence at Mandi for Mr. Mohak</title>",
        "<title>Lighting Audit — Real Plan · Mr. Mohak Residence</title>",
    )
    html = html.replace(
        '<div class="serif text-lg font-light" style="color: var(--ink)">Lighting Audit</div>',
        '<div class="serif text-lg font-light" style="color: var(--ink)">Lighting Audit <span class="text-xs uppercase tracking-wider align-middle ml-2 px-2 py-0.5 rounded" style="background: var(--amber-soft); color: var(--amber)">Real plan</span></div>',
    )

    # Add a nav link for floor plan
    html = html.replace(
        '<a href="#overview" class="nav-room">Overview</a>',
        '<a href="#overview" class="nav-room">Overview</a>\n      <a href="#floor-plan" class="nav-room">Floor plan</a>',
    )

    out_html.write_text(html)
    print(f"wrote {out_html}", file=sys.stderr)


if __name__ == "__main__":
    main()
