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


def _position_axis(
    label_c: float, size: float,
    near_neg: float | None, near_pos: float | None,
) -> tuple[float, float, int]:
    """Position a 1D rectangle of length `size` along an axis.

    The rectangle's length is FIXED at `size` (the architect's declared
    dimension). We only choose where along the axis to place it, anchoring to
    walls when they exist.

    Returns (low_coord, high_coord, walls_used). `walls_used` is 0/1/2 — how
    many cardinal walls actually anchored the position (0 = pure label-rect
    fallback; 2 = both walls confirmed the size).
    """
    half = size / 2
    fit_tolerance = 0.15  # accept "both walls fit" if their sum is within ±15% of size

    # A wall farther from the label than the room's own size in that direction
    # cannot be this room's own wall — it must belong to a neighbour or the
    # building exterior beyond this room. Filter them out before anchoring.
    if near_neg is not None and near_neg > size:
        near_neg = None
    if near_pos is not None and near_pos > size:
        near_pos = None

    if near_neg is not None and near_pos is not None:
        total = near_neg + near_pos
        if abs(total - size) <= fit_tolerance * size:
            # Both walls match the nominal size — anchor to both
            return label_c - near_neg, label_c + near_pos, 2
        # Both walls found but their sum disagrees with the labelled size. Anchor
        # to whichever wall sits closest to the expected half-dimension — that's
        # the credible room edge.
        if abs(near_neg - half) <= abs(near_pos - half):
            return label_c - near_neg, label_c - near_neg + size, 1
        return label_c + near_pos - size, label_c + near_pos, 1

    if near_neg is not None:
        return label_c - near_neg, label_c - near_neg + size, 1
    if near_pos is not None:
        return label_c + near_pos - size, label_c + near_pos, 1

    # No walls found within the room's own size — centre the rectangle on the label
    return label_c - half, label_c + half, 0


def _snap_polygon_to_walls(
    raw: RawLabel,
    width_in: int,
    height_in: int,
    walls: list[Segment],
    other_label_positions: list[tuple[float, float]],  # noqa: ARG001
    *,
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> tuple[list[Point], int]:
    """Build a room polygon at the architect's declared dimensions, anchored to walls.

    The room SIZE is taken as truth from the label's nominal width × height.
    We then position that fixed-size rectangle by finding nearby walls and
    snapping the rectangle's edges to them. If both walls on an axis sum to
    the labelled width, we anchor to both. If only one wall is found (or they
    disagree), we anchor to whichever wall is most credible (closest to the
    expected half-dimension) and extend the rectangle by the labelled width.

    This is more reliable than letting ray-cast distances determine room SIZE —
    the architect already declared the size in the label, so we use that as
    ground truth and only infer position from the walls.

    `other_label_positions` is unused in v2 of this algorithm (kept in the
    signature for backwards compatibility with the floors/extract_rooms call
    site, which still passes neighbour positions).

    Returns (polygon_in_local_meters, walls_anchored_count). `walls_anchored`
    is 0–4 — how many cardinal sides of the polygon came from real walls.
    """
    cx, cy = raw.x_in, raw.y_in
    # Search only as far as the room's own size in each axis — a wall beyond
    # that distance cannot belong to this room. Small buffer (1.1×) to allow
    # for slight off-centre labels.
    max_search_x = width_in * 1.1
    max_search_y = height_in * 1.1

    near_left = _ray_cast_to_wall(cx, cy, -1, 0, max_search_x, walls)
    near_right = _ray_cast_to_wall(cx, cy, +1, 0, max_search_x, walls)
    near_down = _ray_cast_to_wall(cx, cy, 0, -1, max_search_y, walls)
    near_up = _ray_cast_to_wall(cx, cy, 0, +1, max_search_y, walls)

    x_lo, x_hi, x_walls = _position_axis(cx, float(width_in), near_left, near_right)
    y_lo, y_hi, y_walls = _position_axis(cy, float(height_in), near_down, near_up)

    # Convert to local-meter frame
    x_min = (x_lo - region.min_x) * dxf_unit_to_m
    x_max = (x_hi - region.min_x) * dxf_unit_to_m
    y_min = (y_lo - region.min_y) * dxf_unit_to_m
    y_max = (y_hi - region.min_y) * dxf_unit_to_m
    polygon = [
        Point(x=x_min, y=y_min),
        Point(x=x_max, y=y_min),
        Point(x=x_max, y=y_max),
        Point(x=x_min, y=y_max),
    ]
    return polygon, x_walls + y_walls


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

    # Staircases — separate detection because architects mark them with UP/DN
    # arrows, not room labels with dimensions.
    room_counter = _add_staircases(
        msp, anchors, region, room_counter, result,
        default_ceiling_height_m=default_ceiling_height_m,
        dxf_unit_to_m=dxf_unit_to_m,
    )
    return result


# Default nominal staircase dimensions when we have no label dims: 4ft wide ×
# 10ft long (a typical residential straight-run flight).
_STAIRCASE_NOMINAL_W_IN = 48.0
_STAIRCASE_NOMINAL_H_IN = 120.0


def _add_staircases(
    msp: Modelspace,
    anchors: list[FloorAnchor],
    region: PlanRegion,
    room_counter: int,
    result: ExtractRoomsResult,
    *,
    default_ceiling_height_m: float,
    dxf_unit_to_m: float,
) -> int:
    """Detect UP/DN-marked staircases and append one Room per cluster.

    The staircase polygon is a default-sized rectangle centred on the cluster
    centroid (we don't have a labelled dimension to anchor against). Future
    work (v1): snap to surrounding walls or trace the actual tread arcs.

    Staircases on dropped sheets (multi-sheet DXFs) are filtered out by
    requiring the staircase's nearest floor anchor among ALL detected anchors
    to also be in the kept set.
    """
    from lighting_engine.parser.floors import detect_floor_anchors
    from lighting_engine.parser.staircases import detect_staircase_anchors

    stair_anchors = detect_staircase_anchors(msp)

    # Filter to the kept sheet only. We detect floor anchors fresh and check
    # whether each staircase's nearest anchor was kept after sheet dedup.
    all_floor_anchors = detect_floor_anchors(msp)
    if len(all_floor_anchors) > len(anchors):
        kept_set = {(a.name, round(a.x, 2), round(a.y, 2)) for a in anchors}
        def is_in_kept_sheet(s_x: float, s_y: float) -> bool:
            if not all_floor_anchors:
                return True
            idx = nearest_anchor_index((s_x, s_y), all_floor_anchors)
            a = all_floor_anchors[idx]
            return (a.name, round(a.x, 2), round(a.y, 2)) in kept_set
        stair_anchors = [s for s in stair_anchors if is_in_kept_sheet(s.x, s.y)]

    for s in stair_anchors:
        # Assign to floor via the same nearest-anchor logic as labelled rooms
        floor_idx = nearest_anchor_index((s.x, s.y), anchors)
        floor_level = floor_level_for_name(anchors[floor_idx].name)

        # Build a default-size axis-aligned rectangle centred on the cluster
        half_w = _STAIRCASE_NOMINAL_W_IN / 2
        half_h = _STAIRCASE_NOMINAL_H_IN / 2
        x_min = (s.x - half_w - region.min_x) * dxf_unit_to_m
        x_max = (s.x + half_w - region.min_x) * dxf_unit_to_m
        y_min = (s.y - half_h - region.min_y) * dxf_unit_to_m
        y_max = (s.y + half_h - region.min_y) * dxf_unit_to_m
        polygon = [
            Point(x=x_min, y=y_min),
            Point(x=x_max, y=y_min),
            Point(x=x_max, y=y_max),
            Point(x=x_min, y=y_max),
        ]

        room_id = _slugify("STAIRCASE", room_counter)
        room_counter += 1
        result.rooms.append(Room(
            id=room_id,
            name="STAIRCASE",
            type=RoomType.staircase,
            floor_level=floor_level,
            polygon=polygon,
            ceiling_height_m=default_ceiling_height_m,
        ))
    return room_counter


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
    """Slide an axis-aligned rectangle inward if it extrudes past the envelope,
    preserving its size. Falls back to a per-vertex clamp if sliding can't fit
    the polygon (room wider than envelope).
    """
    env_xmin, env_ymin, env_xmax, env_ymax = envelope
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    # Degenerate setup (synthetic tests, weird DXFs): polygon doesn't overlap
    # the envelope at all. Leave polygon alone — slide/clamp would corrupt it.
    if maxx < env_xmin or minx > env_xmax or maxy < env_ymin or miny > env_ymax:
        return polygon

    dx = 0.0
    if maxx > env_xmax:
        dx = env_xmax - maxx          # negative → slide left
    elif minx < env_xmin:
        dx = env_xmin - minx          # positive → slide right
    dy = 0.0
    if maxy > env_ymax:
        dy = env_ymax - maxy
    elif miny < env_ymin:
        dy = env_ymin - miny

    if dx == 0.0 and dy == 0.0:
        return polygon

    slid = [Point(x=p.x + dx, y=p.y + dy) for p in polygon]
    # After slide, did the polygon now extrude the OPPOSITE side? Then it's
    # genuinely wider than the envelope and we fall back to a clamp.
    sxs = [p.x for p in slid]
    sys = [p.y for p in slid]
    if (min(sxs) < env_xmin - 1e-6 or max(sxs) > env_xmax + 1e-6
            or min(sys) < env_ymin - 1e-6 or max(sys) > env_ymax + 1e-6):
        return [
            Point(
                x=max(env_xmin, min(env_xmax, p.x)),
                y=max(env_ymin, min(env_ymax, p.y)),
            )
            for p in polygon
        ]
    return slid


