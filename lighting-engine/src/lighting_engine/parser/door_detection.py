"""Detect door positions from raw DWG primitives.

The architect can draw a door in any of four ways. In residential DWGs the
two strong signals are doors and walls — doors more so, because contractors
need precise positions and a door connects exactly two rooms. Surfacing every
door (not just the easy INSERT case) gives downstream room-positioning a
reliable anchor.

Patterns handled:
  1. ``INSERT`` — block reference to a door symbol library; insert position
     is the door location. Swing geometry unknown.
  2. ``ARC`` — the swing arc itself. Chord midpoint approximates the door
     location; arc radius approximates the door width; mid-angle gives the
     swing orientation.
  3. ``LINE`` / ``LWPOLYLINE`` pair — paired swing-symbol strokes drawn as
     two short segments close to each other. Position is the midpoint of the
     pair; swing geometry not recovered.

Coordinates supplied to this module are in DXF units (typically inches);
results come back in the local-meter frame matching ``PlanRegion``.
"""

import math
from dataclasses import dataclass

from ezdxf.entities.arc import Arc
from ezdxf.entities.insert import Insert
from ezdxf.entities.line import Line
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.layouts.layout import Modelspace

from lighting_engine.parser.geometry import PlanRegion

# Maximum endpoint-to-endpoint distance, in meters, between two LINE / poly
# segments for them to be treated as a swing-symbol pair. Tuned to typical
# door-leaf widths (~0.9m) plus a small slop.
_LINE_PAIR_RADIUS_M = 0.5


@dataclass(frozen=True)
class DoorRaw:
    """A raw door observation from one DWG primitive (or paired primitives).

    Position is in the local-meter frame. ``swing_radius_m`` and
    ``swing_orientation_deg`` are populated only when the source was an ARC
    entity (so the downstream attacher can refine width / swing direction).
    """

    position: tuple[float, float]
    swing_radius_m: float | None
    swing_orientation_deg: float | None
    source_layer: str


def _to_local_m(
    x_in: float,
    y_in: float,
    region: PlanRegion,
    scale: float,
) -> tuple[float, float]:
    return (x_in - region.min_x) * scale, (y_in - region.min_y) * scale


def _arc_midangle_deg(start_deg: float, end_deg: float) -> float:
    """Mid-angle (degrees) of the arc sweeping CCW from start to end.

    DXF arc angles are stored CCW; if end < start the arc wraps through 360.
    """
    sweep = end_deg - start_deg
    if sweep < 0:
        sweep += 360.0
    mid = start_deg + sweep / 2.0
    if mid >= 360.0:
        mid -= 360.0
    return mid


def _collect_inserts(
    msp: Modelspace,
    door_layers: set[str],
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> list[DoorRaw]:
    """Pattern 1: door block references. Position = insert; swing unknown."""
    out: list[DoorRaw] = []
    for e in msp.query("INSERT"):
        if not isinstance(e, Insert):
            continue
        if e.dxf.layer not in door_layers:
            continue
        x_in, y_in = float(e.dxf.insert.x), float(e.dxf.insert.y)
        if not region.contains((x_in, y_in)):
            continue
        local = _to_local_m(x_in, y_in, region, dxf_unit_to_m)
        out.append(DoorRaw(
            position=local,
            swing_radius_m=None,
            swing_orientation_deg=None,
            source_layer=e.dxf.layer,
        ))
    return out


def _collect_arcs(
    msp: Modelspace,
    door_layers: set[str],
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> list[DoorRaw]:
    """Pattern 2: swing arcs. Position = chord midpoint; swing data populated.

    The chord midpoint is the point on the wall the door pivots from (the
    arc's two endpoints span the door's opening width). The arc radius is
    the door width in DXF units; convert to meters. The mid-angle is the
    swing orientation in CCW degrees from the +X axis.
    """
    out: list[DoorRaw] = []
    for e in msp.query("ARC"):
        if not isinstance(e, Arc):
            continue
        if e.dxf.layer not in door_layers:
            continue
        start_pt = e.start_point
        end_pt = e.end_point
        chord_mid_in = (
            (float(start_pt.x) + float(end_pt.x)) / 2.0,
            (float(start_pt.y) + float(end_pt.y)) / 2.0,
        )
        if not region.contains(chord_mid_in):
            continue
        local = _to_local_m(chord_mid_in[0], chord_mid_in[1], region, dxf_unit_to_m)
        out.append(DoorRaw(
            position=local,
            swing_radius_m=float(e.dxf.radius) * dxf_unit_to_m,
            swing_orientation_deg=_arc_midangle_deg(
                float(e.dxf.start_angle), float(e.dxf.end_angle),
            ),
            source_layer=e.dxf.layer,
        ))
    return out


def _collect_segment_pairs(
    msp: Modelspace,
    door_layers: set[str],
    region: PlanRegion,
    dxf_unit_to_m: float,
    *,
    pair_radius_m: float = _LINE_PAIR_RADIUS_M,
) -> list[DoorRaw]:
    """Pattern 3: LINE/LWPOLYLINE pairs. Each cluster of nearby short
    segments becomes one DoorRaw at the cluster midpoint.

    The architect's swing-symbol stroke is typically two short lines close
    together (the door leaf line + a chord/sweep marker). We group by
    proximity (any endpoint of one within ``pair_radius_m`` of any endpoint
    of another) and emit one DoorRaw per cluster. Singletons are also
    emitted — a stray door-layer line is rare but real.
    """
    raw_segments: list[tuple[tuple[float, float], tuple[float, float], str]] = []

    for e in msp.query("LINE"):
        if not isinstance(e, Line):
            continue
        if e.dxf.layer not in door_layers:
            continue
        a_in = (float(e.dxf.start.x), float(e.dxf.start.y))
        b_in = (float(e.dxf.end.x), float(e.dxf.end.y))
        mid_in = ((a_in[0] + b_in[0]) / 2.0, (a_in[1] + b_in[1]) / 2.0)
        if not region.contains(mid_in):
            continue
        a_local = _to_local_m(a_in[0], a_in[1], region, dxf_unit_to_m)
        b_local = _to_local_m(b_in[0], b_in[1], region, dxf_unit_to_m)
        raw_segments.append((a_local, b_local, e.dxf.layer))

    for e in msp.query("LWPOLYLINE"):
        if not isinstance(e, LWPolyline):
            continue
        if e.dxf.layer not in door_layers:
            continue
        verts = [(float(v[0]), float(v[1])) for v in e.get_points()]
        edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for i in range(len(verts) - 1):
            edges.append((verts[i], verts[i + 1]))
        if e.closed and len(verts) >= 3:
            edges.append((verts[-1], verts[0]))
        for a_in, b_in in edges:
            mid_in = ((a_in[0] + b_in[0]) / 2.0, (a_in[1] + b_in[1]) / 2.0)
            if not region.contains(mid_in):
                continue
            a_local = _to_local_m(a_in[0], a_in[1], region, dxf_unit_to_m)
            b_local = _to_local_m(b_in[0], b_in[1], region, dxf_unit_to_m)
            raw_segments.append((a_local, b_local, e.dxf.layer))

    if not raw_segments:
        return []

    # Union-find: any-endpoint proximity. Same approach as
    # ``cluster_window_lines`` but inlined to keep the door module
    # self-contained.
    parent = list(range(len(raw_segments)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    threshold_sq = pair_radius_m * pair_radius_m
    for i in range(len(raw_segments)):
        a_i, b_i, _ = raw_segments[i]
        for j in range(i + 1, len(raw_segments)):
            a_j, b_j, _ = raw_segments[j]
            best_sq = math.inf
            for px, py in (a_i, b_i):
                for qx, qy in (a_j, b_j):
                    d_sq = (px - qx) ** 2 + (py - qy) ** 2
                    if d_sq < best_sq:
                        best_sq = d_sq
            if best_sq <= threshold_sq:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for idx in range(len(raw_segments)):
        root = find(idx)
        groups.setdefault(root, []).append(idx)

    out: list[DoorRaw] = []
    for indices in groups.values():
        xs: list[float] = []
        ys: list[float] = []
        layers: list[str] = []
        for k in indices:
            a, b, layer = raw_segments[k]
            xs.extend([a[0], b[0]])
            ys.extend([a[1], b[1]])
            layers.append(layer)
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        out.append(DoorRaw(
            position=(cx, cy),
            swing_radius_m=None,
            swing_orientation_deg=None,
            source_layer=layers[0],
        ))
    return out


def collect_door_positions(
    msp: Modelspace,
    door_layers: set[str],
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> list[DoorRaw]:
    """Detect every door drawn in ``msp`` on a door-classified layer.

    Combines all three drawing conventions:
      - ``INSERT`` references to door symbol blocks
      - ``ARC`` entities (swing arcs)
      - ``LINE`` / ``LWPOLYLINE`` pairs (swing-symbol strokes)

    Pure function over the modelspace. Order is: INSERTs first, then ARCs,
    then segment-pair clusters (the order downstream attachers see them in
    is not load-bearing — Door IDs are assigned by index in the caller).

    Entities whose source-DXF position falls outside ``region`` are dropped.
    Everything else is converted to the local-meter frame.
    """
    out: list[DoorRaw] = []
    out.extend(_collect_inserts(msp, door_layers, region, dxf_unit_to_m))
    out.extend(_collect_arcs(msp, door_layers, region, dxf_unit_to_m))
    out.extend(_collect_segment_pairs(msp, door_layers, region, dxf_unit_to_m))
    return out
