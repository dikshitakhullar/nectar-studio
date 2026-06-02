"""One-off DXF inspection — what's in the file, what can our parser hope to extract.

Usage:
    uv run python scripts/inspect_dxf.py path/to/file.dxf
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf
from ezdxf.entities import Insert, LWPolyline, MText, Polyline, Text


def inspect(path: Path) -> None:
    print(f"\n=== Inspecting: {path} ===\n")
    doc = ezdxf.readfile(str(path))
    print(f"DXF version: {doc.dxfversion}")
    print(f"Encoding: {doc.encoding}")
    print(f"Header units (INSUNITS): {doc.header.get('$INSUNITS', '?')}  "
          f"(0=unitless · 1=in · 4=mm · 5=cm · 6=m · 2=ft)")

    msp = doc.modelspace()

    # ---- Layers ----
    print(f"\nLayers defined: {len(doc.layers)}")
    layer_entity_counts: Counter[str] = Counter()
    entity_types_per_layer: dict[str, Counter[str]] = defaultdict(Counter)
    for e in msp:
        layer_entity_counts[e.dxf.layer] += 1
        entity_types_per_layer[e.dxf.layer][e.dxftype()] += 1
    print(f"Layers with entities: {len(layer_entity_counts)}")
    print(f"\n--- Top 40 layers by entity count ---")
    for layer, n in layer_entity_counts.most_common(40):
        types = entity_types_per_layer[layer]
        type_summary = ", ".join(f"{t}:{c}" for t, c in types.most_common(4))
        print(f"  {n:>6}   {layer:<40}   {type_summary}")

    # ---- Block definitions ----
    print(f"\nBlock definitions: {len(doc.blocks)}")
    block_insert_counts: Counter[str] = Counter()
    for e in msp.query("INSERT"):
        if isinstance(e, Insert):
            block_insert_counts[e.dxf.name] += 1
    print(f"\n--- Top 40 block references (INSERT) by count ---")
    for name, n in block_insert_counts.most_common(40):
        print(f"  {n:>6}   {name}")

    # ---- Geometry summary ----
    closed_lwpoly = sum(1 for e in msp.query("LWPOLYLINE")
                        if isinstance(e, LWPolyline) and e.closed)
    open_lwpoly = sum(1 for e in msp.query("LWPOLYLINE")
                      if isinstance(e, LWPolyline) and not e.closed)
    closed_poly = sum(1 for e in msp.query("POLYLINE")
                      if isinstance(e, Polyline) and e.is_closed)
    open_poly = sum(1 for e in msp.query("POLYLINE")
                    if isinstance(e, Polyline) and not e.is_closed)
    lines = len(msp.query("LINE"))
    arcs = len(msp.query("ARC"))
    circles = len(msp.query("CIRCLE"))
    texts = len(msp.query("TEXT"))
    mtexts = len(msp.query("MTEXT"))

    print(f"\n--- Geometry counts (overall) ---")
    print(f"  LWPolyline closed:  {closed_lwpoly:>6}   ← candidate room polygons")
    print(f"  LWPolyline open:    {open_lwpoly:>6}")
    print(f"  Polyline closed:    {closed_poly:>6}   ← also candidate room polygons")
    print(f"  Polyline open:      {open_poly:>6}")
    print(f"  Line:               {lines:>6}   ← wall lines if no polygons")
    print(f"  Arc:                {arcs:>6}")
    print(f"  Circle:             {circles:>6}")
    print(f"  Text:               {texts:>6}")
    print(f"  MText:              {mtexts:>6}")

    # ---- Text samples (room labels, dimensions) ----
    print(f"\n--- Sample text content (up to 30) ---")
    text_samples: list[tuple[str, str]] = []
    for e in msp.query("TEXT MTEXT"):
        if isinstance(e, Text):
            t = e.dxf.text.strip()
        elif isinstance(e, MText):
            t = e.text.strip().replace("\\P", " | ")
        else:
            continue
        if t:
            text_samples.append((e.dxf.layer, t))
        if len(text_samples) >= 30:
            break
    for layer, t in text_samples:
        print(f"  [{layer}]  {t[:120]}")

    # ---- Bounding box ----
    try:
        from ezdxf.bbox import extents
        bbox = extents(msp)
        if bbox.has_data:
            mn, mx = bbox.extmin, bbox.extmax
            print(f"\n--- Bounding box (drawing units) ---")
            print(f"  min: ({mn.x:.2f}, {mn.y:.2f})")
            print(f"  max: ({mx.x:.2f}, {mx.y:.2f})")
            print(f"  size: {mx.x - mn.x:.2f} × {mx.y - mn.y:.2f}")
    except Exception as ex:
        print(f"\n(could not compute bbox: {ex})")

    # ---- Heuristic: layers that LOOK like rooms / walls / lighting ----
    role_hints = {
        "rooms": ["room"],
        "walls": ["wall"],
        "windows": ["window", "win"],
        "doors": ["door"],
        "lighting": ["light", "rcp", "downlight", "chandelier", "cove",
                     "fixture", "luminaire", "lamp"],
        "furniture": ["furn"],
        "north": ["north"],
        "heights": ["height", "ceiling", "ch_", "ch-"],
        "dimensions": ["dim"],
        "annotations": ["annot", "text", "label"],
    }
    print(f"\n--- Heuristic layer-name matches ---")
    for role, hints in role_hints.items():
        matched = [layer for layer in layer_entity_counts
                   if any(h in layer.lower() for h in hints)]
        if matched:
            total = sum(layer_entity_counts[layer] for layer in matched)
            print(f"  {role:<14} ({total:>5} entities)  matched layers: {matched[:8]}")


if __name__ == "__main__":
    path = Path(sys.argv[1])
    inspect(path)
