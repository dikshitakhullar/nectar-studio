"""End-to-end smoke test for the LLM-1 + LLM-2 design pipeline.

Run from `lighting-engine/`:

    uv run python scripts/test_design_pipeline.py

Parses the Delhi base fixture, picks BEDROOM-2 (configurable), runs:
  1. LLM-1 (scene understanding)  → RoomScene
  2. LLM-2 (design intent)        → RoomDesign

Prints both outputs and a per-zone summary so a designer can read what
the agent decided and why. Also writes the rendered PNG to /tmp.

Requires ANTHROPIC_API_KEY (loaded from .env.local automatically).
"""

import argparse
import json
import os
import sys
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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", default="BEDROOM - 2")
    parser.add_argument(
        "--fixture",
        default="tests/fixtures/dwgs/real_base_architectural.dxf",
    )
    parser.add_argument(
        "--furniture-fixture",
        default="tests/fixtures/dwgs/real_furniture.dxf",
    )
    parser.add_argument("--ceiling-type", default="cove")
    parser.add_argument(
        "--mood", default="wind_down",
        choices=["cozy", "productive", "wind_down", "entertain"],
    )
    parser.add_argument(
        "--activities", default="reading,naps,mood lighting",
        help="Comma-separated activity list.",
    )
    parser.add_argument(
        "--time-of-use", default="evening,late_night",
        help="Comma-separated subset of: morning,evening,late_night.",
    )
    parser.add_argument(
        "--occupants", default="adult",
        help="Comma-separated subset of: kids,young_adult,adult,elderly.",
    )
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
    from lighting_engine.design.room_render import render_room_for_vision
    from lighting_engine.design.scene_understanding import understand_scene
    from lighting_engine.parser.furniture_merge import merge_furniture_from_file
    from lighting_engine.parser.pipeline import parse_file

    print(f"=> Parsing {args.fixture}")
    project, _ = parse_file(
        Path(args.fixture), project_name="smoke", location="delhi",
    )
    if args.furniture_fixture:
        print(f"=> Merging furniture from {args.furniture_fixture}")
        project, _ = merge_furniture_from_file(
            project, Path(args.furniture_fixture),
        )

    room = next((r for r in project.rooms if r.name == args.room), None)
    if room is None:
        print(f"ERROR: room '{args.room}' not found.")
        return 1
    print(
        f"=> Target: {room.name} (floor={room.floor_level}, "
        f"polygon pts={len(room.polygon)})"
    )

    print("=> Rendering room PNG...")
    png = render_room_for_vision(project=project, room_id=room.id)
    out_path = Path("/tmp/design_input.png")
    out_path.write_bytes(png)
    print(f"   wrote {out_path}")

    print(f"\n=> [LLM-1] Scene understanding (ceiling_type={args.ceiling_type})...")
    scene = understand_scene(
        project=project, room_id=room.id, ceiling_type=args.ceiling_type,
    )
    print("   walls:")
    for w in scene.walls:
        letter = chr(65 + w.wall_index)
        print(f"     {letter}: {w.purpose} (conf {w.confidence:.2f})")
    print("   ceiling:")
    for cz in scene.ceiling:
        print(f"     {cz.type}: {cz.description}")
    print(f"   focal: {[fp.type for fp in scene.focal_points]}")
    print(f"   notes: {scene.notes}")

    brief = DesignerBrief(
        intent_mood=args.mood,
        activities=[a.strip() for a in args.activities.split(",") if a.strip()],
        time_of_use=[t.strip() for t in args.time_of_use.split(",") if t.strip()],  # type: ignore[arg-type]
        occupants=[o.strip() for o in args.occupants.split(",") if o.strip()],  # type: ignore[arg-type]
    )
    standards = StandardsSnapshot(target_lux=150.0, cct_k=2700, cri_min=80)

    print(f"\n=> [LLM-2] Design intent (mood={brief.intent_mood})...")
    design = generate_design(
        scene=scene, brief=brief, standards=standards, catalog=[],
        room_name=room.name, room_type=str(room.type),
    )

    print()
    print("=" * 72)
    print(f"ROOM DESIGN — {room.name}")
    print("=" * 72)
    print(f"\nOverall rationale:")
    print(f"  {design.overall_rationale}")
    print(f"\nZones ({len(design.zones)}):")
    for i, z in enumerate(design.zones, 1):
        print(f"\n  [{i}] {z.intent}  →  {z.target_feature_ref}")
        print(
            f"      archetype={z.fixture_archetype}  "
            f"CCT={z.cct_k}K  CRI≥{z.cri_min}"
            + (f"  beam={z.beam_deg}°" if z.beam_deg else "")
            + (f"  target_lux={z.target_lux}" if z.target_lux else "")
        )
        print(f"      → {z.rationale}")

    print()
    print("=" * 72)
    print("Raw JSON")
    print("=" * 72)
    print(json.dumps(design.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
