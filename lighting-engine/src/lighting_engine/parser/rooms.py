"""Extract `Room` objects by snapping each labeled room to its nearest walls.

Real residential DWGs draw walls as loose LINE segments broken by doors,
so room boundaries never form closed loops `shapely.polygonize` could pick
up. Instead, for each labeled room we cast rays from the label position
outward in the four cardinal directions, find the nearest wall in each, and
snap the polygon's edges to those walls when the hit looks plausible
relative to the label's nominal dimensions. Rooms with no plausible walls
nearby (terraces, courtyards, open spaces) gracefully fall back to a
label-centered rectangle.

This is per-floor: if FLOOR text labels are present, each wall and label is
assigned to its nearest anchor and the ray-cast runs independently per floor.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from ezdxf.entities.mtext import MText
from ezdxf.entities.text import Text
from ezdxf.layouts.layout import Modelspace

from lighting_engine.models.geometry import Point, Room, RoomType
from lighting_engine.parser.floors import (
    FloorAnchor,
    detect_floor_anchors,
    floor_level_for_name,
    nearest_anchor_index,
)
from lighting_engine.parser.geometry import PlanRegion
from lighting_engine.parser.mtext import parse_room_label
from lighting_engine.parser.wall_graph import Segment


@dataclass(frozen=True)
class RawLabel:
    """A text label with its insertion point in DXF units."""

    text: str
    x_in: float
    y_in: float


@dataclass
class ExtractRoomsResult:
    rooms: list[Room] = field(default_factory=list[Room])
    rect_fallback_room_ids: list[str] = field(default_factory=list[str])


# Room-name keyword → canonical type. Order matters: more specific first.
_TYPE_HINTS: list[tuple[tuple[str, ...], RoomType]] = [
    (("MASTER TOILET", "TOILET", "BATH", "WC", "POWDER"), RoomType.bathroom),
    (("MASTER BEDROOM", "BEDROOM", "GUEST"),              RoomType.bedroom),
    (("STUDY",),                                          RoomType.study),
    (("KITCHEN", "PANTRY"),                               RoomType.kitchen),
    (("DINING",),                                         RoomType.dining),
    (("LIVING",),                                         RoomType.living),
    (("FOYER", "ENTRANCE"),                               RoomType.foyer),
    (("LOBBY", "PASSAGE", "CORRIDOR", "HALLWAY"),         RoomType.hallway),
    (("STAIR",),                                          RoomType.staircase),
    (("BALCONY", "TERRACE", "COURTYARD", "PORCH"),        RoomType.outdoor),
]

# Accept a ray-cast wall hit only if it's within this ratio of the nominal
# half-dimension. 0.5–1.5 = ±50% — generous enough for shape variation,
# tight enough to reject walls of adjacent rooms or stray interior features.
_HIT_RATIO_MIN = 0.5
_HIT_RATIO_MAX = 1.5
# A room needs at least this many sides snapped to real walls before we
# consider it "wall-anchored" (vs. flagging as a label-rect fallback).
_MIN_SNAPPED_SIDES_TO_NOT_FALLBACK = 2


def infer_room_type(name: str) -> RoomType:
    upper = name.upper()
    for keywords, rt in _TYPE_HINTS:
        if any(k in upper for k in keywords):
            return rt
    return RoomType.unknown


def _slugify(name: str, index: int) -> str:
    base = "-".join(name.lower().split())
    return f"{base or 'room'}-{index:02d}"


def _collect_dimensioned_labels(msp: Modelspace) -> list[tuple[RawLabel, str, int, int]]:
    out: list[tuple[RawLabel, str, int, int]] = []
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
        name, w, h = parse_room_label(raw)
        if w is None or h is None:
            continue
        out.append((
            RawLabel(text=raw, x_in=float(ip.x), y_in=float(ip.y)),
            name, w, h,
        ))
    return out


def _ray_cast_to_wall(
    cx: float, cy: float, dx: int, dy: int, max_dist: float,
    walls: Iterable[Segment],
) -> float | None:
    """Cast an axis-aligned ray from (cx, cy) in direction (dx, dy).

    `dx` and `dy` are -1/0/+1 — exactly one is non-zero (we only handle the
    four cardinal directions). Returns signed distance to the nearest wall
    LINE the ray crosses, or None if no wall is hit within `max_dist`.
    """
    best: float | None = None
    for (x1, y1), (x2, y2) in walls:
        if dx != 0 and min(y1, y2) <= cy <= max(y1, y2) and y1 != y2:
            # Horizontal ray at y=cy. Wall must straddle cy and not be horizontal.
            t = (cy - y1) / (y2 - y1)
            xi = x1 + t * (x2 - x1)
            dist = (xi - cx) * dx
            if 0 < dist < max_dist and (best is None or dist < best):
                best = dist
        if dy != 0 and min(x1, x2) <= cx <= max(x1, x2) and x1 != x2:
            # Vertical ray at x=cx. Wall must straddle cx and not be vertical.
            t = (cx - x1) / (x2 - x1)
            yi = y1 + t * (y2 - y1)
            dist = (yi - cy) * dy
            if 0 < dist < max_dist and (best is None or dist < best):
                best = dist
    return best


def _snap_polygon_to_walls(
    raw: RawLabel,
    width_in: int,
    height_in: int,
    walls: list[Segment],
    *,
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> tuple[list[Point], int]:
    """Build a room polygon by snapping each side to the nearest wall.

    Returns (polygon_in_local_meters, snapped_sides_count). The polygon is
    always a 4-point rectangle; `snapped_sides_count` is how many of its
    four edges came from actual wall hits (the rest fell back to nominal).
    """
    cx, cy = raw.x_in, raw.y_in
    hw_nom = width_in / 2
    hh_nom = height_in / 2
    max_search = max(width_in, height_in) * 1.5

    def pick(hit: float | None, half_nom: float) -> tuple[float, bool]:
        if hit is None:
            return half_nom, False
        ratio = hit / half_nom
        if _HIT_RATIO_MIN <= ratio <= _HIT_RATIO_MAX:
            return hit, True
        return half_nom, False

    left, l_ok = pick(_ray_cast_to_wall(cx, cy, -1, 0, max_search, walls), hw_nom)
    right, r_ok = pick(_ray_cast_to_wall(cx, cy, +1, 0, max_search, walls), hw_nom)
    down, d_ok = pick(_ray_cast_to_wall(cx, cy, 0, -1, max_search, walls), hh_nom)
    up, u_ok = pick(_ray_cast_to_wall(cx, cy, 0, +1, max_search, walls), hh_nom)

    # Convert to local-meter frame
    x_min = (cx - left - region.min_x) * dxf_unit_to_m
    x_max = (cx + right - region.min_x) * dxf_unit_to_m
    y_min = (cy - down - region.min_y) * dxf_unit_to_m
    y_max = (cy + up - region.min_y) * dxf_unit_to_m
    polygon = [
        Point(x=x_min, y=y_min),
        Point(x=x_max, y=y_min),
        Point(x=x_max, y=y_max),
        Point(x=x_min, y=y_max),
    ]
    return polygon, sum([l_ok, r_ok, d_ok, u_ok])


def _select_main_sheet(
    anchors: list[FloorAnchor],
    labels: list[tuple[RawLabel, str, int, int]],
    segments: list[Segment],
    *,
    same_sheet_y_gap: float = 500.0,
) -> tuple[list[FloorAnchor], list[tuple[RawLabel, str, int, int]], list[Segment]]:
    """Drop duplicate sheets when one DXF contains the same plan drawn twice.

    Many architectural DXFs contain multiple "sheets" laid out side by side
    (e.g. a base architectural sheet and an annotated one) — each with its own
    set of FLOOR labels. We detect duplicate sheets by name-counting: if two
    or more floor anchors share a name (e.g. two 'GROUND FLOOR' labels), we
    cluster anchors by Y, pick the sheet with the most labels, and drop
    everything else.

    Returns (kept_anchors, kept_labels, kept_segments). If no duplicate sheets
    are detected the input is returned unchanged.
    """
    if not anchors:
        return anchors, labels, segments
    name_counts = Counter(a.name for a in anchors)
    if max(name_counts.values()) < 2:
        return anchors, labels, segments

    # Y-cluster the anchors so each cluster is one sheet
    sorted_anchors = sorted(anchors, key=lambda a: a.y)
    sheets: list[list[FloorAnchor]] = [[sorted_anchors[0]]]
    for a in sorted_anchors[1:]:
        if a.y - sheets[-1][-1].y > same_sheet_y_gap:
            sheets.append([a])
        else:
            sheets[-1].append(a)
    if len(sheets) < 2:
        return anchors, labels, segments

    # Boundaries between sheets = midpoint between adjacent sheet Y centres
    centres = [sum(a.y for a in s) / len(s) for s in sheets]

    def sheet_y_range(i: int) -> tuple[float, float]:
        ymin = float("-inf") if i == 0 else (centres[i - 1] + centres[i]) / 2
        ymax = float("inf") if i == len(sheets) - 1 else (centres[i] + centres[i + 1]) / 2
        return ymin, ymax

    # Pick the sheet whose Y band contains the most labels
    best_i = 0
    best_count = -1
    for i in range(len(sheets)):
        ymin, ymax = sheet_y_range(i)
        n = sum(1 for raw, *_ in labels if ymin <= raw.y_in <= ymax)
        if n > best_count:
            best_count = n
            best_i = i

    ymin, ymax = sheet_y_range(best_i)
    kept_anchors = sheets[best_i]
    kept_labels = [item for item in labels if ymin <= item[0].y_in <= ymax]
    kept_segments = [
        ((x1, y1), (x2, y2))
        for ((x1, y1), (x2, y2)) in segments
        if ymin <= (y1 + y2) / 2 <= ymax
    ]
    return kept_anchors, kept_labels, kept_segments


def extract_rooms(
    msp: Modelspace,
    region: PlanRegion,
    wall_segments: Iterable[Segment],
    *,
    default_ceiling_height_m: float = 2.7,
    dxf_unit_to_m: float = 0.0254,
) -> ExtractRoomsResult:
    """Extract `Room` objects per floor by ray-casting labels to nearest walls."""
    in_region_segments = [
        ((x1, y1), (x2, y2))
        for (x1, y1), (x2, y2) in wall_segments
        if region.contains(((x1 + x2) / 2, (y1 + y2) / 2))
    ]

    labels = _collect_dimensioned_labels(msp)
    in_region_labels = [
        (r, n, w, h) for r, n, w, h in labels if region.contains((r.x_in, r.y_in))
    ]

    # Detect floors. If none, synthesise a single anchor at the region centre.
    anchors = detect_floor_anchors(msp)
    if not anchors:
        anchors = [FloorAnchor(
            name="GROUND",
            x=(region.min_x + region.max_x) / 2,
            y=(region.min_y + region.max_y) / 2,
        )]

    # If multiple anchors share a name, we have a multi-sheet DXF — keep only
    # the densest sheet so each room is counted once.
    anchors, in_region_labels, in_region_segments = _select_main_sheet(
        anchors, in_region_labels, in_region_segments,
    )

    # Bucket segments and labels by nearest anchor
    seg_buckets: dict[int, list[Segment]] = {i: [] for i in range(len(anchors))}
    for seg in in_region_segments:
        mid = ((seg[0][0] + seg[1][0]) / 2, (seg[0][1] + seg[1][1]) / 2)
        seg_buckets[nearest_anchor_index(mid, anchors)].append(seg)
    label_buckets: dict[int, list[tuple[RawLabel, str, int, int]]] = {
        i: [] for i in range(len(anchors))
    }
    for raw, name, w, h in in_region_labels:
        label_buckets[nearest_anchor_index((raw.x_in, raw.y_in), anchors)].append(
            (raw, name, w, h)
        )

    # Per-floor dedup: drop labels with the same name AND same nominal dims
    # within a floor (architects rarely have two rooms identical on the same
    # floor; collisions usually indicate a duplicate sheet that survived the
    # Y-cluster filter).
    for floor_idx, bucket in label_buckets.items():
        seen: set[tuple[str, int, int]] = set()
        dedup: list[tuple[RawLabel, str, int, int]] = []
        for raw, name, w, h in bucket:
            key = (name, w, h)
            if key not in seen:
                dedup.append((raw, name, w, h))
                seen.add(key)
        label_buckets[floor_idx] = dedup

    result = ExtractRoomsResult()
    room_counter = 0
    for floor_idx, anchor in enumerate(anchors):
        floor_level = floor_level_for_name(anchor.name)
        floor_walls = seg_buckets[floor_idx]
        for raw, name, w_in, h_in in label_buckets[floor_idx]:
            room_id = _slugify(name, room_counter)
            room_counter += 1
            polygon, snapped_sides = _snap_polygon_to_walls(
                raw, w_in, h_in, floor_walls,
                region=region, dxf_unit_to_m=dxf_unit_to_m,
            )
            if snapped_sides < _MIN_SNAPPED_SIDES_TO_NOT_FALLBACK:
                result.rect_fallback_room_ids.append(room_id)
            result.rooms.append(Room(
                id=room_id,
                name=name,
                type=infer_room_type(name),
                floor_level=floor_level,
                polygon=polygon,
                ceiling_height_m=default_ceiling_height_m,
            ))
    return result
