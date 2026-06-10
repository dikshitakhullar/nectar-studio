"""Analyze an RCP (reflected ceiling plan) DWG/DXF and print a what's-inside report.

This is a diagnostic, NOT a parser. It tells us what entities, layers, blocks,
and text annotations live in the RCP — so we can design the real parser
based on real data instead of guessing.

Run from `lighting-engine/`:
  uv run python scripts/analyze_rcp_dwg.py /path/to/your/RCP-GROUND-FLOOR.dwg

DWG is auto-converted to DXF via LibreDWG's dwg2dxf (already a project dep).
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to the RCP DWG or DXF file.")
    parser.add_argument(
        "--top-blocks", type=int, default=15,
        help="How many top block references to list (by count).",
    )
    parser.add_argument(
        "--text-samples", type=int, default=40,
        help="How many sample TEXT/MTEXT entries to print.",
    )
    args = parser.parse_args(argv)

    src = Path(args.path)
    if not src.exists():
        print(f"ERROR: file not found: {src}")
        return 1

    dxf_path = _ensure_dxf(src)
    print(f"=> Analyzing {dxf_path}\n")

    import ezdxf

    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    # 1. High-level summary
    print("━" * 78)
    print("ENTITY TYPE COUNTS")
    print("━" * 78)
    type_counts: Counter[str] = Counter()
    for ent in msp:
        type_counts[ent.dxftype()] += 1
    for etype, n in type_counts.most_common():
        print(f"  {etype:18s} {n:6d}")

    # 2. Layers + entity counts per layer
    print("\n" + "━" * 78)
    print("LAYERS (sorted by entity count)")
    print("━" * 78)
    layer_counts: Counter[str] = Counter()
    layer_types: dict[str, Counter[str]] = defaultdict(Counter)
    for ent in msp:
        layer = ent.dxf.layer
        layer_counts[layer] += 1
        layer_types[layer][ent.dxftype()] += 1
    for layer, n in layer_counts.most_common():
        top_types = ", ".join(
            f"{t}={c}" for t, c in layer_types[layer].most_common(4)
        )
        print(f"  {layer:32s} {n:6d}  ({top_types})")

    # 3. Block references — name + count + a sample of attribute text
    print("\n" + "━" * 78)
    print(f"TOP {args.top_blocks} BLOCK REFERENCES (likely fixtures)")
    print("━" * 78)
    block_counts: Counter[str] = Counter()
    block_layers: dict[str, Counter[str]] = defaultdict(Counter)
    block_samples: dict[str, tuple[float, float]] = {}
    for ent in msp.query("INSERT"):
        name = ent.dxf.name
        block_counts[name] += 1
        block_layers[name][ent.dxf.layer] += 1
        if name not in block_samples:
            ins = ent.dxf.insert
            block_samples[name] = (ins.x, ins.y)
    for name, n in block_counts.most_common(args.top_blocks):
        layer = block_layers[name].most_common(1)[0][0]
        sx, sy = block_samples[name]
        print(
            f"  {name:36s} ×{n:4d}  layer={layer:24s}  sample=({sx:.1f},{sy:.1f})"
        )

    # 4. Text annotations
    print("\n" + "━" * 78)
    print(f"TEXT / MTEXT ANNOTATIONS (sample of {args.text_samples})")
    print("━" * 78)
    text_entries: list[tuple[str, float, float, str]] = []
    for ent in msp.query("TEXT MTEXT"):
        text_val = (
            ent.dxf.text if ent.dxftype() == "TEXT"
            else _mtext_plain(ent)
        )
        text_val = text_val.strip()
        if not text_val:
            continue
        ins = ent.dxf.insert if ent.dxftype() == "TEXT" else ent.dxf.insert
        text_entries.append((
            ent.dxftype(), ins.x, ins.y, text_val,
        ))
    # Group by likely category: ceiling level marker (LVL), room name, dim
    lvl_pattern = re.compile(r"^LVL\s*[+-]?", re.IGNORECASE)
    dim_pattern = re.compile(r"^\d[\d'\-\"\s.½¼¾]*$")
    lvl_texts = [t for t in text_entries if lvl_pattern.search(t[3])]
    dim_texts = [t for t in text_entries if dim_pattern.match(t[3])]
    other_texts = [
        t for t in text_entries
        if not lvl_pattern.search(t[3]) and not dim_pattern.match(t[3])
    ]
    print(
        f"\n  Total text entries: {len(text_entries)}\n"
        f"  LVL markers (level callouts): {len(lvl_texts)}\n"
        f"  Dimension annotations:        {len(dim_texts)}\n"
        f"  Other (room names, notes):    {len(other_texts)}\n"
    )

    print("  --- LVL markers (first 15) ---")
    for _, x, y, val in lvl_texts[:15]:
        print(f"    ({x:>7.1f},{y:>7.1f})  {val}")

    print("\n  --- Other text (room names, notes — first {0}) ---".format(
        args.text_samples
    ))
    for _, x, y, val in other_texts[:args.text_samples]:
        print(f"    ({x:>7.1f},{y:>7.1f})  {val}")

    # 5. Polyline summary (cove, level zones, decorations are usually polylines)
    print("\n" + "━" * 78)
    print("POLYLINES BY LAYER (top 10 — these are usually cove/level/feature boundaries)")
    print("━" * 78)
    poly_by_layer: Counter[str] = Counter()
    for ent in msp.query("LWPOLYLINE POLYLINE"):
        poly_by_layer[ent.dxf.layer] += 1
    for layer, n in poly_by_layer.most_common(10):
        print(f"  {layer:32s} {n:6d}")

    # 6. Hatches (often used for ceiling-zone fills, metal-ceiling pattern)
    print("\n" + "━" * 78)
    print("HATCHES BY LAYER (usually ceiling-zone fills or decorative patterns)")
    print("━" * 78)
    hatch_by_layer: Counter[str] = Counter()
    for ent in msp.query("HATCH"):
        hatch_by_layer[ent.dxf.layer] += 1
    for layer, n in hatch_by_layer.most_common(10):
        print(f"  {layer:32s} {n:6d}")

    print()
    print("━" * 78)
    print("HEURISTIC GUESSES (for the next-step RCP parser)")
    print("━" * 78)
    # Guess which blocks are downlights / chandeliers
    downlight_candidates = [
        name for name, n in block_counts.most_common(20)
        if n >= 5 and any(kw in name.upper() for kw in (
            "DOWN", "LIGHT", "LAMP", "LED", "DL", "FIX", "REC",
        ))
    ]
    chandelier_candidates = [
        name for name, n in block_counts.most_common(20)
        if any(kw in name.upper() for kw in (
            "CHAND", "PEND", "HANG", "STATEMENT", "LAMP",
        ))
    ]
    print(f"  Possible downlight blocks: {downlight_candidates or '(none obvious by name)'}")
    print(f"  Possible chandelier/pendant blocks: {chandelier_candidates or '(none obvious by name)'}")
    print(f"  LVL text markers found: {len(lvl_texts)} (these are the ceiling level zones)")
    print(f"  Polyline layers (likely cove/zone outlines): "
          f"{[name for name, _ in poly_by_layer.most_common(5)]}")
    print()
    print("Share this report — I'll use it to design the RCP parser.")
    return 0


def _ensure_dxf(src: Path) -> Path:
    """Return a DXF path. If `src` is DWG, convert to a temp DXF via dwg2dxf."""
    if src.suffix.lower() == ".dxf":
        return src
    if src.suffix.lower() != ".dwg":
        print(f"WARNING: unrecognized extension {src.suffix}, trying as DXF")
        return src
    out_dir = Path(tempfile.mkdtemp(prefix="rcp_analyze_"))
    # dwg2dxf writes the .dxf next to its CWD; copy to a temp dir for cleanliness
    tmp_dwg = out_dir / src.name
    shutil.copy(src, tmp_dwg)
    print(f"=> Converting DWG → DXF via dwg2dxf...")
    result = subprocess.run(
        ["dwg2dxf", tmp_dwg.name],
        cwd=out_dir, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"WARNING: dwg2dxf returned {result.returncode}")
        print(result.stderr)
    out_dxf = out_dir / src.with_suffix(".dxf").name
    if not out_dxf.exists():
        print(f"ERROR: expected {out_dxf} after conversion, not found")
        sys.exit(1)
    return out_dxf


def _mtext_plain(ent) -> str:
    """Strip MTEXT formatting codes ({\\f...}, {\\C...}, etc.)."""
    raw = ent.text or ""
    return re.sub(r"\\[A-Za-z][^;]*;|\{|\}", "", raw).strip()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
