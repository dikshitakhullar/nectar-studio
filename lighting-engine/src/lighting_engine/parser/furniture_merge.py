"""Merge a furniture-only DWG/DXF into an already-parsed architectural Project.

The v1 designer hands us two CAD files: a ceiling/architectural plan and a
furniture-layout plan. ``parser.pipeline.parse_file`` is built for the former
(rooms come from labels + walls). When the furniture sits on a *separate* sheet
— which is the rule, not the exception, for the Delhi designer fixture —
``parse_file`` returns zero furniture for the rooms.

This module fills that gap. It parses the furniture file independently, then
**attaches** its furniture entities to the rooms of an existing ``Project``.

Coordinate-frame registration is the load-bearing problem here. Per the
project memory (``project_lighting_agent.md``), furniture and architectural
files *usually* share a coordinate frame on real Delhi drawings — but not
always. We detect alignment empirically rather than assume it: count how many
furniture positions fall inside *some* parsed room polygon and, if the
"inlier ratio" is below an evidence threshold, brute-force search for an
``(dx, dy)`` offset that maximises inliers.

The function is pure: ``Project + Path → (Project, MergeReport)``. It does not
mutate the input project (we operate on a deep-copy) and emits diagnostics via
the report rather than logs.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from ezdxf.entities.insert import Insert
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.entities.mtext import MText
from ezdxf.entities.text import Text
from ezdxf.layouts.layout import Modelspace
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.models.geometry import (
    Furniture,
    Point,
    Project,
)
from lighting_engine.parser.geometry import PlanRegion, find_plan_region
from lighting_engine.parser.layers import LayerRole, classify_layers
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.mtext import strip_mtext_codes

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# DXF default unit assumption (inches, matching ``parser.pipeline.INCH_TO_M``).
_INCH_TO_M = 0.0254

# Inlier ratio above which the file is assumed to share the architectural
# coordinate frame. 0.5 means "more than half the furniture entities sit
# inside *some* room polygon" — strong enough evidence that we trust the raw
# coordinates without searching for an offset.
_INLIER_THRESHOLD = 0.5

# Brute-force offset search grid (meters). We try a square grid of dx/dy
# offsets around (0, 0) when the zero-offset inlier ratio is below threshold.
# ±5m / 0.5m step → 21×21 = 441 candidates. Big enough to cover the kinds of
# drift we've seen between Delhi sheets (≤ a few metres) without the cost of
# a finer search. If a real file ever needs more, the report's
# ``inlier_ratio`` will still surface as low and a follow-up pass can widen.
_MAX_OFFSET_M = 5.0
_OFFSET_STEP_M = 0.5

# Minimum points required for boundary-driven region detection to be
# trustworthy. With fewer than this we'd get a near-zero-area region (because
# a 1- or 2-point cluster collapses to its bbox), so we fall back to all-
# centroid clustering. 8 ≈ a small room's 4 walls each split into 2 segments
# — anything less and the architect probably didn't include the shell.
_MIN_BOUNDARY_POINTS = 8

# Appliance-style TEXT labels we treat as furniture markers when no
# furniture-layer INSERT is nearby. Block names on real Delhi furniture files
# are sometimes meaningful ("sofa 053") and sometimes garbage; text labels
# next to a fixture position are a complementary signal. Frozen at module
# load — these are stable English-language appliance words.
_APPLIANCE_WORDS: frozenset[str] = frozenset({
    "FIREPLACE",
    "SINK",
    "FRIDGE",
    "MICROWAVE",
    "DRESSER",
    "RANGE",
    "OVEN",
    "TUB",
    "SHOWER",
    "TOILET",
    "BED",
    "SOFA",
    "DINING TABLE",
    "COFFEE TABLE",
})


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MergeReport:
    """Diagnostics from a furniture-merge run.

    Returned alongside the (mutated) project so callers can surface
    misalignment warnings or assess how confident the merge was.

    Fields:
        furniture_seen: total furniture-like entities found in the file
            (INSERT blocks on furniture layers + appliance TEXT labels).
        furniture_attached: how many ended up routed into a Room.
        dropped_outside_rooms: ``furniture_seen - furniture_attached`` —
            entities that fell outside every room polygon after registration
            (typically: outdoor furniture, residual misalignment, or stray
            title-block markers we didn't filter).
        offset_applied_m: the ``(dx, dy)`` we added to furniture positions
            before routing. ``(0.0, 0.0)`` when the files shared a frame.
        inlier_ratio: fraction of furniture entities that fell inside some
            room polygon under ``offset_applied_m``. Studio surfaces a
            warning when this is < 0.5 even after the offset search.
    """

    furniture_seen: int
    furniture_attached: int
    dropped_outside_rooms: int
    offset_applied_m: tuple[float, float]
    inlier_ratio: float


# ---------------------------------------------------------------------------
# Helpers — geometry / collection
# ---------------------------------------------------------------------------

def _shapely_rooms(project: Project) -> list[ShapelyPolygon]:
    """Materialise each room's polygon as a shapely Polygon for containment tests."""
    return [
        ShapelyPolygon([(p.x, p.y) for p in r.polygon])
        for r in project.rooms
    ]


def _local_meters(
    x_in: float, y_in: float, region: PlanRegion, scale: float,
) -> tuple[float, float]:
    """Convert raw DXF coords to the furniture file's local-meter frame."""
    return (x_in - region.min_x) * scale, (y_in - region.min_y) * scale


def _rooms_centroid(project: Project) -> tuple[float, float]:
    """Mean (x, y) of all room-polygon vertices in the architectural frame.

    Used as the architectural anchor when computing the hint offset:
    aligning the furniture-candidate centroid with the rooms centroid puts
    the bulk of the furniture roughly on top of the bulk of the rooms,
    which is the right starting point for the brute-force inlier search.

    Centroid-of-vertices (rather than centroid-of-polygons) is intentional
    — large rooms with more vertices pull the anchor slightly toward
    themselves, which is what we want because larger rooms contain more
    furniture.
    """
    xs: list[float] = []
    ys: list[float] = []
    for room in project.rooms:
        for p in room.polygon:
            xs.append(p.x)
            ys.append(p.y)
    if not xs or not ys:
        return 0.0, 0.0
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _positions_centroid(
    positions: list[tuple[float, float]],
) -> tuple[float, float]:
    """Mean (x, y) of a position list. Empty list → (0, 0)."""
    if not positions:
        return 0.0, 0.0
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _collect_boundary_centroids(
    msp: Modelspace, wall_layers: set[str], window_layers: set[str],
) -> list[tuple[float, float]]:
    """Centroids of LINE/LWPOLYLINE edges on wall+window layers.

    Used as the input to ``find_plan_region`` for the furniture file. We
    accept either wall OR window layers as boundary evidence because some
    furniture files lack a dedicated wall layer (architects copy the
    architectural shell as a faded background sometimes only as polylines or
    not at all). Falls back to "everything" if both are empty — handled by
    the caller.
    """
    out: list[tuple[float, float]] = []
    layers = wall_layers | window_layers
    for e in msp.query("LINE"):
        if e.dxf.layer not in layers:
            continue
        out.append((
            (float(e.dxf.start.x) + float(e.dxf.end.x)) / 2.0,
            (float(e.dxf.start.y) + float(e.dxf.end.y)) / 2.0,
        ))
    for e in msp.query("LWPOLYLINE"):
        if not isinstance(e, LWPolyline):
            continue
        if e.dxf.layer not in layers:
            continue
        verts = [(float(v[0]), float(v[1])) for v in e.get_points()]
        if not verts:
            continue
        cx = sum(v[0] for v in verts) / len(verts)
        cy = sum(v[1] for v in verts) / len(verts)
        out.append((cx, cy))
    return out


def _collect_all_centroids(msp: Modelspace) -> list[tuple[float, float]]:
    """Fallback: centroids of every drawable entity in the modelspace.

    Used when no wall/window-layer linework is present in the furniture file
    — we still need a plan region to translate coords into the local-meter
    frame, so we cluster from the bulk linework's centroid bbox.
    """
    out: list[tuple[float, float]] = []
    for e in msp.query("LINE"):
        out.append((
            (float(e.dxf.start.x) + float(e.dxf.end.x)) / 2.0,
            (float(e.dxf.start.y) + float(e.dxf.end.y)) / 2.0,
        ))
    for e in msp.query("LWPOLYLINE"):
        if not isinstance(e, LWPolyline):
            continue
        verts = [(float(v[0]), float(v[1])) for v in e.get_points()]
        if not verts:
            continue
        cx = sum(v[0] for v in verts) / len(verts)
        cy = sum(v[1] for v in verts) / len(verts)
        out.append((cx, cy))
    for e in msp.query("INSERT"):
        if not isinstance(e, Insert):
            continue
        out.append((float(e.dxf.insert.x), float(e.dxf.insert.y)))
    return out


@dataclass(frozen=True)
class _FurnitureCandidate:
    """One furniture entity collected from the furniture file, in
    furniture-local meters (i.e. region-shifted)."""

    position: tuple[float, float]
    raw_label: str | None
    source: str  # "insert" or "label"


# Word-boundary check: an appliance match must be a whole word, not a
# substring of a longer label. Compiled once at module load.
_APPLIANCE_PATTERNS: dict[str, re.Pattern[str]] = {
    word: re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    for word in _APPLIANCE_WORDS
}


def _match_appliance_label(text: str) -> str | None:
    """Return the appliance word found in ``text`` (if any), uppercase, else None."""
    cleaned = strip_mtext_codes(text).upper()
    for word, pat in _APPLIANCE_PATTERNS.items():
        if pat.search(cleaned):
            return word
    return None


def _collect_furniture_candidates(
    msp: Modelspace,
    furniture_layers: set[str],
    region: PlanRegion,
    scale: float,
) -> list[_FurnitureCandidate]:
    """Walk the modelspace; emit furniture candidates in furniture-local meters.

    Sources (combined):
      * INSERT blocks on layers classified as ``LayerRole.furniture``.
      * MTEXT/TEXT entities anywhere in the modelspace whose content matches
        an appliance word (FIREPLACE / SINK / FRIDGE / …).

    We accept entities whose raw DXF coords fall inside ``region``; the
    region was computed from the bulk linework so out-of-region positions
    are typically title-block stragglers we want to drop.
    """
    out: list[_FurnitureCandidate] = []

    for e in msp.query("INSERT"):
        if not isinstance(e, Insert):
            continue
        if e.dxf.layer not in furniture_layers:
            continue
        x_raw, y_raw = float(e.dxf.insert.x), float(e.dxf.insert.y)
        if not region.contains((x_raw, y_raw)):
            continue
        lx, ly = _local_meters(x_raw, y_raw, region, scale)
        out.append(_FurnitureCandidate(
            position=(lx, ly),
            raw_label=e.dxf.name,
            source="insert",
        ))

    for e in msp.query("MTEXT TEXT"):
        if isinstance(e, MText):
            raw = e.text
        elif isinstance(e, Text):
            raw = e.dxf.text
        else:
            continue
        try:
            ip = e.dxf.insert
        except AttributeError:
            continue
        x_raw, y_raw = float(ip.x), float(ip.y)
        if not region.contains((x_raw, y_raw)):
            continue
        appliance = _match_appliance_label(raw)
        if appliance is None:
            continue
        lx, ly = _local_meters(x_raw, y_raw, region, scale)
        out.append(_FurnitureCandidate(
            position=(lx, ly),
            raw_label=appliance,
            source="label",
        ))

    return out


# ---------------------------------------------------------------------------
# Coordinate-frame registration
# ---------------------------------------------------------------------------

def _count_inliers(
    positions: list[tuple[float, float]],
    room_polys: list[ShapelyPolygon],
    offset: tuple[float, float],
) -> int:
    """Count how many ``positions`` fall inside *some* room polygon under ``offset``."""
    if not positions or not room_polys:
        return 0
    dx, dy = offset
    inliers = 0
    for x, y in positions:
        p = ShapelyPoint(x + dx, y + dy)
        for poly in room_polys:
            if poly.contains(p):
                inliers += 1
                break
    return inliers


def _detect_offset(
    positions: list[tuple[float, float]],
    room_polys: list[ShapelyPolygon],
) -> tuple[tuple[float, float], float]:
    """Find the (dx, dy) offset that maximises inliers; return (offset, ratio).

    Strategy:
      1. Try ``(0, 0)`` first. If inlier ratio ≥ ``_INLIER_THRESHOLD``,
         accept it (the files share a frame — the common case).
      2. Otherwise, brute-force search a ±``_MAX_OFFSET_M`` grid in
         ``_OFFSET_STEP_M`` steps and keep the (dx, dy) with the highest
         inlier count. Ties broken by smaller magnitude (prefer the offset
         closer to zero so we don't fabricate large translations on noisy
         data).

    Returns:
        ``((dx, dy), inlier_ratio)`` where ``inlier_ratio = best_inliers /
        len(positions)``. When ``positions`` is empty, returns
        ``((0.0, 0.0), 0.0)``.
    """
    total = len(positions)
    if total == 0 or not room_polys:
        return (0.0, 0.0), 0.0

    zero_inliers = _count_inliers(positions, room_polys, (0.0, 0.0))
    zero_ratio = zero_inliers / total
    if zero_ratio >= _INLIER_THRESHOLD:
        return (0.0, 0.0), zero_ratio

    best_offset = (0.0, 0.0)
    best_inliers = zero_inliers
    best_mag = 0.0

    # Pre-compute step count so float drift doesn't off-by-one the grid.
    # The full grid is bounded (~441 candidates by default), so we exhaust
    # it rather than early-exit at the threshold — early-exit gave
    # mediocre offsets when the threshold was met by a less-good candidate
    # before the global optimum.
    steps = int(round(_MAX_OFFSET_M / _OFFSET_STEP_M))
    for i in range(-steps, steps + 1):
        dx = i * _OFFSET_STEP_M
        for j in range(-steps, steps + 1):
            dy = j * _OFFSET_STEP_M
            if dx == 0.0 and dy == 0.0:
                continue  # already evaluated above
            inliers = _count_inliers(positions, room_polys, (dx, dy))
            mag = math.hypot(dx, dy)
            if inliers > best_inliers or (
                inliers == best_inliers and 0.0 < mag < best_mag
            ):
                best_inliers = inliers
                best_offset = (dx, dy)
                best_mag = mag

    return best_offset, best_inliers / total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_furniture_from_file(
    project: Project,
    furniture_path: Path,
    *,
    dxf_unit_to_m: float = _INCH_TO_M,
) -> tuple[Project, MergeReport]:
    """Parse a furniture DWG/DXF and attach its furniture to ``project``'s rooms.

    The furniture file is loaded via the same robust pipeline as
    architectural files (LibreDWG + sanitizer + ezdxf recover). Furniture
    candidates are collected from:

      * ``INSERT`` blocks on layers classified as
        :data:`LayerRole.furniture` (the FURNITURE layer in the Delhi
        fixture, plus any layer whose name contains "sofa", "bed",
        "cupboard").
      * ``TEXT`` / ``MTEXT`` entities anywhere in the modelspace whose
        content matches a known appliance word
        (FIREPLACE / SINK / FRIDGE / MICROWAVE / etc).

    Coordinate frames are reconciled empirically: we try zero-offset first
    and brute-force search a ±5 m grid only if fewer than half of the
    furniture entities land in some room polygon. The applied offset and
    inlier ratio are returned in the :class:`MergeReport` for the studio
    to surface as a "furniture file looks misaligned" warning.

    The function is pure with respect to the input — it operates on a
    deep copy of ``project`` and returns the mutated copy.

    Args:
        project: An architectural project whose rooms are already populated.
            Used unchanged; the returned project is a copy.
        furniture_path: Path to a ``.dwg`` or ``.dxf`` containing the
            furniture layout. May reside in a different coordinate frame than
            the architectural file — we detect and correct.
        dxf_unit_to_m: Scaling factor from raw DXF units to meters. Defaults
            to inches (matching the Delhi residential convention).

    Returns:
        ``(mutated_project, report)``. The project's ``rooms[i].furniture``
        lists are appended to in place on the copy.
    """
    # Deep-ish copy via Pydantic — model_copy(deep=True) gives us a fresh
    # tree we can mutate without touching the caller's project.
    mutated = project.model_copy(deep=True)

    load = load_drawing(furniture_path)
    doc = load.document
    msp = doc.modelspace()

    layer_names = [layer.dxf.name for layer in doc.layers]
    layer_roles = classify_layers(layer_names)
    wall_layers = set(layer_roles.get(LayerRole.wall, []))
    window_layers = set(layer_roles.get(LayerRole.window, []))
    furniture_layers = set(layer_roles.get(LayerRole.furniture, []))

    # Determine the furniture file's plan region. Prefer wall/window
    # centroids (the architectural shell the furniture sheet usually shows
    # faded); fall back to all-entity centroids so we still get a region
    # when the file is furniture-only with no shell — *or* when the shell
    # exists but is embedded inside block references (xref-style), in which
    # case the wall layer's direct linework is too sparse to define a region.
    boundary_pts = _collect_boundary_centroids(msp, wall_layers, window_layers)
    if len(boundary_pts) < _MIN_BOUNDARY_POINTS:
        boundary_pts = _collect_all_centroids(msp)
    if not boundary_pts:
        # Furniture file has no entities at all — nothing to merge.
        return mutated, MergeReport(
            furniture_seen=0,
            furniture_attached=0,
            dropped_outside_rooms=0,
            offset_applied_m=(0.0, 0.0),
            inlier_ratio=0.0,
        )

    region = find_plan_region(boundary_pts)

    candidates = _collect_furniture_candidates(
        msp, furniture_layers, region, dxf_unit_to_m,
    )

    room_polys = _shapely_rooms(mutated)

    # Compute a hint offset by aligning the furniture-candidate centroid
    # with the architectural-rooms centroid. Both frames are already in
    # local meters but their origins (find_plan_region's bottom-left of the
    # dominant cluster) don't coincide when the furniture file's plan
    # region is wider/offset relative to the architectural file's. The
    # centroid-to-centroid alignment places the bulk of the furniture
    # roughly on top of the bulk of the rooms — usually within a few
    # metres of the true offset — and the brute-force search refines.
    cand_positions: list[tuple[float, float]] = [c.position for c in candidates]
    arch_centroid = _rooms_centroid(mutated)
    furn_centroid = _positions_centroid(cand_positions)
    hint_offset = (
        arch_centroid[0] - furn_centroid[0],
        arch_centroid[1] - furn_centroid[1],
    )

    # Apply the hint as the search starting point: positions in
    # "hint-shifted" local meters, then add (dx, dy) on top.
    hinted_positions: list[tuple[float, float]] = [
        (p[0] + hint_offset[0], p[1] + hint_offset[1])
        for p in cand_positions
    ]

    offset, inlier_ratio = _detect_offset(hinted_positions, room_polys)
    # The offset we report includes the hint, since both are applied to the
    # raw furniture-local coordinates before routing.
    total_offset = (hint_offset[0] + offset[0], hint_offset[1] + offset[1])

    attached = 0
    dropped = 0
    for cand in candidates:
        lx = cand.position[0] + total_offset[0]
        ly = cand.position[1] + total_offset[1]
        room_idx = _containing_room_index(room_polys, (lx, ly))
        if room_idx is None:
            dropped += 1
            continue
        room = mutated.rooms[room_idx]
        room.furniture.append(_furniture_from_candidate(
            cand, lx, ly, len(room.furniture),
        ))
        attached += 1

    return mutated, MergeReport(
        furniture_seen=len(candidates),
        furniture_attached=attached,
        dropped_outside_rooms=dropped,
        offset_applied_m=total_offset,
        inlier_ratio=inlier_ratio,
    )


def _containing_room_index(
    room_polys: list[ShapelyPolygon],
    point: tuple[float, float],
) -> int | None:
    """Index of the first room polygon containing ``point``, or None."""
    p = ShapelyPoint(point)
    for i, poly in enumerate(room_polys):
        if poly.contains(p):
            return i
    return None


def _furniture_from_candidate(
    cand: _FurnitureCandidate, lx: float, ly: float, existing_count: int,
) -> Furniture:
    """Build a :class:`Furniture` from a candidate. ID uses the existing
    per-room furniture count so IDs stay unique within a room."""
    # Sticky-suffix the ID so merged furniture is distinguishable from
    # whatever the architectural-file's ``attach_entities`` may already
    # have attached on the same room. Same scheme as the ceiling parser
    # ("furn-NNN") but with a "-m" marker.
    return Furniture(
        id=f"furn-m-{existing_count:03d}",
        raw_label=cand.raw_label,
        type="unknown",
        position=Point(x=lx, y=ly),
    )
