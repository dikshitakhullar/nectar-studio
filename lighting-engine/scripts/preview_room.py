"""Render one room's proposed plan as a standalone HTML file you can open in
the browser to give visual feedback.

Run from `lighting-engine/`:
  uv run python scripts/preview_room.py --room "DRAWING ROOM"

Output: /tmp/room_preview.html with the RCP SVG + furniture SVG + zone
breakdown + design rationale. Open it in any browser.
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path


def load_env_local() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / ".env.local"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


# Per-room context — same defaults as the walkthrough script.
DEFAULTS_BY_ROOM = {
    "DRAWING ROOM": {
        "ceiling_type": "multi_level",
        "mood": "entertain",
        "activities": ["entertaining", "conversation"],
        "time_of_use": ["evening", "late_night"],
        "occupants": ["adult"],
    },
    "DINING": {
        "ceiling_type": "cove",
        "mood": "entertain",
        "activities": ["dining"],
        "time_of_use": ["evening"],
        "occupants": ["adult"],
    },
    "FAMILY LOUNGE": {
        "ceiling_type": "multi_level",
        "mood": "cozy",
        "activities": ["family TV", "conversation"],
        "time_of_use": ["evening", "late_night"],
        "occupants": ["adult", "kids"],
    },
    "GUEST BEDROOM": {
        "ceiling_type": "cove",
        "mood": "wind_down",
        "activities": ["reading", "naps"],
        "time_of_use": ["evening", "late_night"],
        "occupants": ["adult"],
    },
    "KITCHEN": {
        "ceiling_type": "flat",
        "mood": "productive",
        "activities": ["dining"],
        "time_of_use": ["morning", "evening"],
        "occupants": ["adult"],
    },
    "BEDROOM - 2": {
        "ceiling_type": "cove",
        "mood": "wind_down",
        "activities": ["reading", "naps"],
        "time_of_use": ["evening", "late_night"],
        "occupants": ["elderly"],
    },
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", default="DRAWING ROOM")
    parser.add_argument("--out", default="/tmp/room_preview.html")
    parser.add_argument("--no-open", action="store_true",
                        help="Don't auto-open the browser")
    args = parser.parse_args(argv)

    load_env_local()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.")
        return 1

    from lighting_engine.brief.models import (
        DesignerBrief,
        StandardsSnapshot,
    )
    from lighting_engine.design.intent_generator import generate_design
    from lighting_engine.design.placement import place_design
    from lighting_engine.design.scene_understanding import understand_scene
    from lighting_engine.lighting.standards import get_lux_standard
    from lighting_engine.parser.furniture_merge import merge_furniture_from_file
    from lighting_engine.parser.pipeline import parse_file
    from lighting_engine.render.rcp import render_rcp_svg

    ctx = DEFAULTS_BY_ROOM.get(args.room)
    if ctx is None:
        print(
            f"ERROR: no default context for room '{args.room}'. "
            f"Add a DEFAULTS_BY_ROOM entry or pick from: "
            f"{list(DEFAULTS_BY_ROOM.keys())}"
        )
        return 1

    print(f"=> Parsing Delhi fixtures...")
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_base_architectural.dxf"),
        project_name="delhi", location="delhi",
    )
    project, _ = merge_furniture_from_file(
        project, Path("tests/fixtures/dwgs/real_furniture.dxf"),
    )
    room = next((r for r in project.rooms if r.name == args.room), None)
    if room is None:
        print(f"ERROR: room '{args.room}' not found.")
        return 1

    print(f"=> {room.name}: scene...")
    scene = understand_scene(
        project=project, room_id=room.id,
        ceiling_type=ctx["ceiling_type"],
    )

    print(f"=> {room.name}: design...")
    brief = DesignerBrief(
        intent_mood=ctx["mood"],
        activities=ctx["activities"],
        time_of_use=ctx["time_of_use"],
        occupants=ctx["occupants"],
    )
    standard = get_lux_standard(str(room.type))
    standards = StandardsSnapshot(
        target_lux=standard.target_lux,
        cct_k=standard.cct_k,
        cri_min=standard.cri_min,
    )
    design = generate_design(
        scene=scene, brief=brief, standards=standards, catalog=[],
        room_name=room.name, room_type=str(room.type),
    )

    print(f"=> {room.name}: placement...")
    fixtures = place_design(design=design, room=room, scene=scene)

    print(f"=> {room.name}: rendering RCP SVG...")
    rcp_svg = render_rcp_svg(room, fixtures)

    # Build the HTML preview.
    html = _build_html(
        room=room, scene=scene, design=design,
        fixtures=fixtures, rcp_svg=rcp_svg, ctx=ctx,
    )
    out_path = Path(args.out)
    out_path.write_text(html)
    print(f"\n=> Wrote {out_path}")

    if not args.no_open:
        url = f"file://{out_path.absolute()}"
        print(f"=> Opening {url} in browser...")
        webbrowser.open(url)
    return 0


def _build_html(*, room, scene, design, fixtures, rcp_svg, ctx) -> str:
    # Walls table
    wall_rows = "\n".join(
        f"<tr><td>{chr(65 + w.wall_index)}</td><td>{w.purpose}</td>"
        f"<td>{w.confidence:.2f}</td></tr>"
        for w in scene.walls
    )
    ceiling_rows = "\n".join(
        f"<tr><td>{cz.type}</td><td>{cz.description}</td></tr>"
        for cz in scene.ceiling
    )
    focal_rows = "\n".join(
        f"<tr><td>{fp.type}</td>"
        f"<td>{fp.position.x:.1f}, {fp.position.y:.1f}</td>"
        f"<td>{fp.purpose_hint}</td></tr>"
        for fp in scene.focal_points
    )

    # Zones table
    zone_rows = "\n".join(
        f"<tr><td><b>{z.intent}</b></td><td>{z.target_feature_ref}</td>"
        f"<td>{z.fixture_archetype}</td><td>{z.cct_k}K</td>"
        f"<td>{z.rationale}</td></tr>"
        for z in design.zones
    )

    # Per-layer fixture summary
    by_layer: dict[str, list] = {}
    for f in fixtures:
        by_layer.setdefault(f.layer.value, []).append(f)
    layer_summary = "\n".join(
        f"<tr><td><b>{layer}</b></td><td>{len(items)}</td></tr>"
        for layer, items in sorted(by_layer.items())
    )

    # All fixtures detail
    fixture_rows = "\n".join(
        f"<tr><td>{f.layer.value}</td><td>{f.type}</td>"
        f"<td>{f.position.x:.2f}, {f.position.y:.2f}</td>"
        f"<td>{f.cct_k}K</td><td>{f.wattage_w}W</td>"
        f"<td>{f.beam_angle_deg or '-'}°</td>"
        f"<td>{f.reasoning}</td></tr>"
        for f in fixtures
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{room.name} — Preview</title>
<style>
  body {{ font: 14px ui-sans-serif, system-ui; max-width: 1100px; margin: 24px auto;
         color: #1c1917; padding: 0 24px; }}
  h1 {{ font-weight: 400; margin: 0 0 6px; }}
  h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;
        color: #b45309; margin-top: 28px; }}
  .meta {{ color: #57534e; font-size: 13px; margin-bottom: 18px; }}
  .rcp {{ background: #fff; border: 1px solid #e7e5e4; border-radius: 8px;
          padding: 24px; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px;
           margin-bottom: 12px; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }}
  th {{ color: #78716c; font-weight: 500; }}
  .rationale {{ background: #fef3c7; border-left: 3px solid #b45309;
                padding: 14px 18px; border-radius: 4px; line-height: 1.6;
                margin-bottom: 8px; }}
  details summary {{ cursor: pointer; color: #78716c; font-size: 13px; }}
  details[open] summary {{ margin-bottom: 12px; }}
  .total {{ font-size: 18px; font-weight: 600; }}
</style>
</head>
<body>

<h1>{room.name}</h1>
<div class="meta">
  Floor {room.floor_level} · parsed type <b>{room.type}</b> ·
  polygon {len(room.polygon)} pts ·
  doors {len(room.doors)} ·
  windows {len(room.windows)} ·
  parsed furniture {len(room.furniture)}
  <br>
  Designer ctx: ceiling=<b>{ctx['ceiling_type']}</b> ·
  mood=<b>{ctx['mood']}</b> ·
  occupants={ctx['occupants']} ·
  time_of_use={ctx['time_of_use']}
</div>

<h2>Reflected ceiling plan ({len(fixtures)} fixtures total)</h2>
<div class="rcp">{rcp_svg}</div>
<table>
  <tr><th>Layer</th><th>Count</th></tr>
  {layer_summary}
</table>

<h2>Design rationale</h2>
<div class="rationale">{design.overall_rationale}</div>

<h2>What the agent saw (RoomScene)</h2>
<h3>Walls</h3>
<table>
  <tr><th>Wall</th><th>Purpose</th><th>Conf</th></tr>
  {wall_rows}
</table>
<h3>Ceiling</h3>
<table>
  <tr><th>Type</th><th>Description</th></tr>
  {ceiling_rows}
</table>
<h3>Focal points</h3>
<table>
  <tr><th>Type</th><th>Position (m)</th><th>Hint</th></tr>
  {focal_rows}
</table>

<h2>Design zones ({len(design.zones)})</h2>
<table>
  <tr><th>Intent</th><th>Target</th><th>Archetype</th><th>CCT</th><th>Rationale</th></tr>
  {zone_rows}
</table>

<details>
  <summary>All {len(fixtures)} placed fixtures (click to expand)</summary>
  <table>
    <tr><th>Layer</th><th>Type</th><th>x,y (m)</th><th>CCT</th><th>W</th><th>Beam</th><th>Reasoning</th></tr>
    {fixture_rows}
  </table>
</details>

</body></html>"""


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
