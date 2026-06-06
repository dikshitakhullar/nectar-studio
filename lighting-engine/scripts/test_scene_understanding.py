"""End-to-end smoke test for LLM-1 scene understanding.

Run from `lighting-engine/`:

    uv run python scripts/test_scene_understanding.py

Parses the Delhi base fixture, renders BEDROOM-2 as a PNG, calls Claude
Opus 4.7 with vision, prints the resulting RoomScene as readable JSON.
Also writes the rendered PNG to /tmp/scene_input.png so you can eyeball
what Claude saw.

Requires ANTHROPIC_API_KEY in env (loaded from .env.local automatically).
"""

import argparse
import json
import os
import sys
from pathlib import Path


def load_env_local() -> None:
    """Read .env.local from the repo root and stuff into os.environ.

    Why not python-dotenv? One less dep. The format we support is the
    simple `KEY=value` shape (no shell expansion, no multi-line values).
    """
    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / ".env.local"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--room", default="BEDROOM - 2",
        help="Room name to test (case-sensitive). Default: 'BEDROOM - 2'.",
    )
    parser.add_argument(
        "--fixture",
        default="tests/fixtures/dwgs/real_base_architectural.dxf",
        help="DXF fixture path (relative to lighting-engine/).",
    )
    parser.add_argument(
        "--furniture-fixture",
        default="tests/fixtures/dwgs/real_furniture.dxf",
        help="Furniture DXF (set to '' to skip).",
    )
    parser.add_argument(
        "--ceiling-type", default="cove",
        help="Ceiling type tag passed to LLM-1 (cove / flat / multi_level / ...).",
    )
    args = parser.parse_args(argv)

    load_env_local()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set (looked in env + .env.local).")
        return 1

    from lighting_engine.design.room_render import render_room_for_vision
    from lighting_engine.design.scene_understanding import understand_scene
    from lighting_engine.parser.furniture_merge import merge_furniture_from_file
    from lighting_engine.parser.pipeline import parse_file

    print(f"=> Parsing {args.fixture}")
    project, _ = parse_file(
        Path(args.fixture),
        project_name="smoke", location="delhi",
    )
    if args.furniture_fixture:
        print(f"=> Merging furniture from {args.furniture_fixture}")
        project, report = merge_furniture_from_file(
            project, Path(args.furniture_fixture),
        )
        print(
            f"   {report.furniture_seen} candidates → "
            f"{report.furniture_attached} attached"
        )

    room = next((r for r in project.rooms if r.name == args.room), None)
    if room is None:
        print(f"ERROR: room '{args.room}' not found.")
        print(f"Available rooms: {[r.name for r in project.rooms[:30]]}")
        return 1
    print(
        f"=> Target: {room.name} (id={room.id}, floor={room.floor_level}, "
        f"polygon pts={len(room.polygon)}, doors={len(room.doors)}, "
        f"windows={len(room.windows)}, furniture={len(room.furniture)})"
    )

    print("=> Rendering room PNG...")
    png = render_room_for_vision(project=project, room_id=room.id)
    out_path = Path("/tmp/scene_input.png")
    out_path.write_bytes(png)
    print(f"   wrote {out_path} ({len(png)} bytes)")
    print("   (open this file to see what Claude saw)")

    print(f"=> Calling Claude Opus 4.7 with ceiling_type='{args.ceiling_type}'...")
    scene = understand_scene(
        project=project, room_id=room.id, ceiling_type=args.ceiling_type,
    )

    print()
    print("=" * 72)
    print("ROOM SCENE (output of LLM-1)")
    print("=" * 72)
    print(json.dumps(scene.model_dump(mode="json"), indent=2))
    print()

    # Human-readable summary
    print("-" * 72)
    print("SUMMARY")
    print("-" * 72)
    for w in scene.walls:
        letter = chr(65 + w.wall_index)
        print(f"  Wall {letter}: {w.purpose} (confidence {w.confidence:.2f})")
        for f in w.features:
            print(f"     - {f}")
    print()
    print("  Ceiling:")
    for cz in scene.ceiling:
        print(f"   - {cz.type}: {cz.description}")
    print()
    print("  Focal points:")
    for fp in scene.focal_points:
        print(
            f"   - {fp.type} at ({fp.position.x:.1f}, {fp.position.y:.1f}): "
            f"{fp.purpose_hint}"
        )
    print()
    print(f"  Notes: {scene.notes}")
    print(f"  Overall confidence: {scene.confidence:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
