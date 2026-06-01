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

# A room needs at least this many sides anchored to a wall or neighbour
# midpoint before we consider it "snapped" (vs. flagging as a label-rect
# fallback for the gaps report).
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


def _nearest_other_label(
    cx: float, cy: float, dx: int, dy: int, max_dist: float,
    others: Iterable[tuple[float, float]],
    perp_tol: float,
) -> float | None:
    """Find the nearest OTHER label in the cardinal direction (dx, dy).

    A neighbor counts as "in this direction" if its forward distance is
    positive and its perpendicular offset from the ray is < perp_tol. Returns
    the forward distance to the closest such neighbor, or None.
    """
    best: float | None = None
    for lx, ly in others:
        if dx != 0:
            forward = (lx - cx) * dx
            perp = abs(ly - cy)
            if (0 < forward < max_dist and perp < perp_tol
                    and (best is None or forward < best)):
                best = forward
        if dy != 0:
            forward = (ly - cy) * dy
            perp = abs(lx - cx)
            if (0 < forward < max_dist and perp < perp_tol
                    and (best is None or forward < best)):
                best = forward
    return best


def _snap_polygon_to_walls(
    raw: RawLabel,
    width_in: int,
    height_in: int,
    walls: list[Segment],
    other_label_positions: list[tuple[float, float]],
    *,
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> tuple[list[Point], int]:
    """Build a room polygon bounded by the closer of: nearest wall, or midpoint
    to the nearest neighbour label in each direction.

    The midpoint constraint solves two problems the wall-only ray-cast cannot:
    (a) doorway openings let a ray run past the room's true wall into the next
        room — the neighbour's midpoint stops the ray first;
    (b) open-plan spaces have no walls between adjacent labels — the midpoint
        becomes the boundary, ensuring rooms don't overlap.

    Returns (polygon_in_local_meters, snapped_sides_count). `snapped_sides`
    is how many of the four edges came from a wall OR a neighbour midpoint
    (i.e. anchored to real geometry rather than nominal-label fallback).
    """
    cx, cy = raw.x_in, raw.y_in
    hw_nom = width_in / 2
    hh_nom = height_in / 2
    max_search = max(width_in, height_in) * 1.5

    # If a wall is found within this multiple of the nominal half-dim, trust it
    # over a neighbour midpoint. Beyond that, the ray likely slipped through a
    # doorway and hit the next room's far wall — better to use the neighbour
    # midpoint as a Voronoi boundary instead.
    # 2.5 is permissive: real rooms can be larger than the label's nominal
    # dimensions (architects often label usable area, not bbox). Tighter ratios
    # caused real rooms (DINING, BAR, FAMILY LOUNGE on the Delhi file) to clip
    # short of their actual walls.
    wall_trust_ratio = 2.5

    def boundary(dx: int, dy: int, half_nom: float, perp_tol: float) -> tuple[float, bool]:
        wall = _ray_cast_to_wall(cx, cy, dx, dy, max_search, walls)
        neighbour = _nearest_other_label(
            cx, cy, dx, dy, max_search, other_label_positions, perp_tol,
        )
        # 1. Wall within sensible range → trust it (architect's actual room boundary)
        if wall is not None and wall <= wall_trust_ratio * half_nom:
            return wall, True
        # 2. No sensible wall → use neighbour midpoint (Voronoi boundary).
        #    This handles open-plan spaces AND doorway slip-throughs where the
        #    ray ran past the room's true wall into the neighbour's space.
        if neighbour is not None:
            return neighbour / 2, True
        # 3. No neighbour either → use the wall even if far (better than nothing)
        if wall is not None:
            return wall, True
        # 4. Nothing at all → fall back to nominal half-dim
        return half_nom, False

    # Perp tolerance = the *other* nominal dim. A horizontal neighbour counts
    # if its Y is within this room's height; a vertical neighbour if its X is
    # within this room's width.
    left, l_ok = boundary(-1, 0, hw_nom, perp_tol=height_in)
    right, r_ok = boundary(+1, 0, hw_nom, perp_tol=height_in)
    down, d_ok = boundary(0, -1, hh_nom, perp_tol=width_in)
    up, u_ok = boundary(0, +1, hh_nom, perp_tol=width_in)

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
        floor_labels = label_buckets[floor_idx]

        # Building envelope for this floor (in local-meter frame). Rooms can't
        # extend past where the actual walls are — this prevents edge-of-building
        # rooms from extruding outward into empty space when no wall stops the
        # ray on their outer side.
        envelope = _floor_envelope_meters(
            floor_walls, region=region, dxf_unit_to_m=dxf_unit_to_m,
        )

        # All label positions on this floor — each room sees the others as
        # potential boundary-stopping neighbours (Voronoi-clip on ray-cast).
        all_positions = [(r.x_in, r.y_in) for r, _, _, _ in floor_labels]
        for raw, name, w_in, h_in in floor_labels:
            room_id = _slugify(name, room_counter)
            room_counter += 1
            my_pos = (raw.x_in, raw.y_in)
            others = [p for p in all_positions if p != my_pos]
            polygon, snapped_sides = _snap_polygon_to_walls(
                raw, w_in, h_in, floor_walls, others,
                region=region, dxf_unit_to_m=dxf_unit_to_m,
            )
            if envelope is not None:
                polygon = _clip_polygon_to_envelope(polygon, envelope)
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


def _floor_envelope_meters(
    floor_walls: list[Segment],
    *,
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> tuple[float, float, float, float] | None:
    """Return (xmin, ymin, xmax, ymax) bbox of walls in local-meter frame."""
    if not floor_walls:
        return None
    xs = [v for seg in floor_walls for v in (seg[0][0], seg[1][0])]
    ys = [v for seg in floor_walls for v in (seg[0][1], seg[1][1])]
    return (
        (min(xs) - region.min_x) * dxf_unit_to_m,
        (min(ys) - region.min_y) * dxf_unit_to_m,
        (max(xs) - region.min_x) * dxf_unit_to_m,
        (max(ys) - region.min_y) * dxf_unit_to_m,
    )


def _clip_polygon_to_envelope(
    polygon: list[Point],
    envelope: tuple[float, float, float, float],
) -> list[Point]:
    """Clamp each polygon vertex into the envelope bbox. Polygons are
    axis-aligned 4-point rectangles in our pipeline so a per-vertex clamp is
    equivalent to a proper rectangle-rectangle intersection.

    If clipping would collapse a side to zero (room entirely outside envelope —
    shouldn't happen given the parser flow), we leave the polygon untouched so
    pydantic's polygon validator still passes.
    """
    env_xmin, env_ymin, env_xmax, env_ymax = envelope
    clipped = [
        Point(
            x=max(env_xmin, min(env_xmax, p.x)),
            y=max(env_ymin, min(env_ymax, p.y)),
        )
        for p in polygon
    ]
    xs = [p.x for p in clipped]
    ys = [p.y for p in clipped]
    if max(xs) - min(xs) < 1e-6 or max(ys) - min(ys) < 1e-6:
        return polygon
    return clipped
