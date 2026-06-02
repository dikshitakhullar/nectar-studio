"""Compute a ProjectDigest from a parsed Project IR.

This is pure derivation: no I/O, no parser dependency. The IR is the source of
truth; the digest re-presents it as resolved facts a language model can reason
over (wall orientations, opening positions on walls, room adjacencies).
"""

import math
from collections import Counter

from lighting_engine.digest.models import (
    Adjacency,
    OpeningOnWall,
    ProjectDigest,
    RoomDigest,
    WallOrientation,
    WallSegment,
)
from lighting_engine.models.geometry import Project, Room, RoomType


def compute_digest(project: Project) -> ProjectDigest:
    """Turn a parsed Project into a ProjectDigest."""
    rooms = [_room_digest(r, project.north_orientation_deg) for r in project.rooms]
    adjacencies = _compute_adjacencies(project.rooms)
    return ProjectDigest(
        project_id=project.id,
        project_name=project.name,
        north_orientation_deg=project.north_orientation_deg,
        rooms=rooms,
        adjacencies=adjacencies,
    )


# ---------------------------------------------------------------------------
# Per-room digest
# ---------------------------------------------------------------------------


def _room_digest(room: Room, north_deg: float) -> RoomDigest:
    walls = _compute_walls(room, north_deg)
    openings = _gather_openings(room)
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    bbox_w = max(xs) - min(xs)
    bbox_h = max(ys) - min(ys)
    aspect = max(bbox_w, bbox_h) / max(min(bbox_w, bbox_h), 1e-6)
    is_outdoor = room.type == RoomType.outdoor

    notes = _qualitative_notes(room, walls, openings, bbox_w, bbox_h, aspect)
    summary = _compose_summary(room, walls, openings, bbox_w, bbox_h, notes)

    return RoomDigest(
        room_id=room.id,
        name=room.name,
        type=room.type,
        floor_level=room.floor_level,
        area_sqm=room.area_sqm,
        bbox_w_m=bbox_w,
        bbox_h_m=bbox_h,
        aspect_ratio=aspect,
        ceiling_height_m=room.ceiling_height_m,
        walls=walls,
        openings=openings,
        furniture_count=len(room.furniture),
        existing_fixture_count=len(room.existing_fixtures),
        is_outdoor=is_outdoor,
        notes=notes,
        summary=summary,
    )


def _compute_walls(room: Room, north_deg: float) -> list[WallSegment]:
    """For each polygon edge, compute its outward-normal orientation."""
    poly = room.polygon
    cx = sum(p.x for p in poly) / len(poly)
    cy = sum(p.y for p in poly) / len(poly)

    walls: list[WallSegment] = []
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        # Midpoint of the edge
        mx = (a.x + b.x) / 2
        my = (a.y + b.y) / 2
        # Outward normal direction = from centroid to edge midpoint
        nx = mx - cx
        ny = my - cy
        orientation = _direction_to_orientation(nx, ny, north_deg)
        length = math.hypot(b.x - a.x, b.y - a.y)
        if length <= 0:
            continue
        walls.append(WallSegment(
            index=i,
            orientation=orientation,
            length_m=length,
            start=a,
            end=b,
        ))
    return walls


def _direction_to_orientation(nx: float, ny: float, north_deg: float) -> WallOrientation:
    """Map a direction vector to an 8-way compass orientation.

    With north_deg=0, +Y in the local frame points North. north_deg rotates the
    compass clockwise (e.g. north_deg=90 means +Y points East, so a wall whose
    normal is +Y is on the East side of the building).
    """
    if nx == 0 and ny == 0:
        return WallOrientation.N
    # Angle measured clockwise from +Y (= North when north_deg=0)
    angle = math.degrees(math.atan2(nx, ny))
    # Compensate for the project's north rotation
    true_heading = (angle - north_deg) % 360
    # 8 sectors of 45°, centred on the compass points
    if true_heading < 22.5 or true_heading >= 337.5:
        return WallOrientation.N
    if true_heading < 67.5:
        return WallOrientation.NE
    if true_heading < 112.5:
        return WallOrientation.E
    if true_heading < 157.5:
        return WallOrientation.SE
    if true_heading < 202.5:
        return WallOrientation.S
    if true_heading < 247.5:
        return WallOrientation.SW
    if true_heading < 292.5:
        return WallOrientation.W
    return WallOrientation.NW


def _gather_openings(room: Room) -> list[OpeningOnWall]:
    """Collect Window/Door entries with their wall_index/along_wall set."""
    out: list[OpeningOnWall] = []
    for d in room.doors:
        if d.wall_index is None or d.along_wall is None:
            continue
        out.append(OpeningOnWall(
            kind="door",
            id=d.id,
            wall_index=d.wall_index,
            along_wall=d.along_wall,
            width_m=d.width_m,
        ))
    for w in room.windows:
        if w.wall_index is None or w.along_wall is None:
            continue
        out.append(OpeningOnWall(
            kind="glazed_door" if w.is_glazed_door else "window",
            id=w.id,
            wall_index=w.wall_index,
            along_wall=w.along_wall,
            width_m=w.width_m,
        ))
    return out


# ---------------------------------------------------------------------------
# Adjacency graph
# ---------------------------------------------------------------------------


def _compute_adjacencies(rooms: list[Room]) -> list[Adjacency]:
    """Pair rooms whose polygons share a door — for now, defined as: two rooms
    on the same floor, each with a door, whose door-bearing wall edges are
    close together (within 0.5m in local-meter space).

    This is a v0 approximation. A proper implementation would track which DXF
    door INSERT contains points from both rooms' boundaries; v1 will refine.
    """
    if not rooms:
        return []
    adjacencies: list[Adjacency] = []
    door_points: list[tuple[Room, tuple[float, float]]] = []
    for r in rooms:
        for d in r.doors:
            if d.wall_index is None or d.along_wall is None:
                continue
            if d.wall_index >= len(r.polygon):
                continue
            a = r.polygon[d.wall_index]
            b = r.polygon[(d.wall_index + 1) % len(r.polygon)]
            px = a.x + d.along_wall * (b.x - a.x)
            py = a.y + d.along_wall * (b.y - a.y)
            door_points.append((r, (px, py)))

    threshold_sq = 0.5 * 0.5
    seen: set[tuple[str, str]] = set()
    for i, (r1, p1) in enumerate(door_points):
        for r2, p2 in door_points[i + 1:]:
            if r1.id == r2.id or r1.floor_level != r2.floor_level:
                continue
            dx = p1[0] - p2[0]
            dy = p1[1] - p2[1]
            if dx * dx + dy * dy > threshold_sq:
                continue
            key = tuple(sorted([r1.id, r2.id]))
            if key in seen:
                continue
            seen.add(key)
            adjacencies.append(Adjacency(
                room_a_id=key[0], room_b_id=key[1], via="door",
            ))
    return adjacencies


# ---------------------------------------------------------------------------
# Qualitative notes + summary text
# ---------------------------------------------------------------------------


def _qualitative_notes(
    room: Room,
    walls: list[WallSegment],
    openings: list[OpeningOnWall],
    bbox_w: float,
    bbox_h: float,
    aspect: float,
) -> list[str]:
    notes: list[str] = []

    # Shape
    if aspect > 3.0:
        notes.append(f"long, narrow shape (aspect {aspect:.1f}:1)")
    elif aspect < 1.2:
        notes.append("roughly square")

    # Daylight: which compass directions face windows
    win_orients = Counter(
        walls[o.wall_index].orientation
        for o in openings
        if o.kind in ("window", "glazed_door") and o.wall_index < len(walls)
    )
    if win_orients:
        facings = ", ".join(f"{o.value} ×{n}" for o, n in win_orients.most_common())
        notes.append(f"windows face: {facings}")
    elif room.type != RoomType.outdoor:
        notes.append("no windows — interior room")

    # Ceiling height
    if room.ceiling_height_m >= 3.5:
        notes.append("high ceiling (≥3.5m)")
    elif room.ceiling_height_m < 2.5:
        notes.append("low ceiling (<2.5m)")

    # Existing fixtures
    if room.existing_fixtures:
        notes.append(f"{len(room.existing_fixtures)} existing fixture(s) detected")

    return notes


def _compose_summary(
    room: Room,
    walls: list[WallSegment],
    openings: list[OpeningOnWall],
    bbox_w: float,
    bbox_h: float,
    notes: list[str],
) -> str:
    """A short, human/LLM-readable paragraph summarising the room."""
    doors = sum(1 for o in openings if o.kind == "door")
    windows = sum(1 for o in openings if o.kind in ("window", "glazed_door"))
    lines = [
        f"{room.name} (floor {room.floor_level}, type={room.type.value})",
        f"  {bbox_w:.1f}m × {bbox_h:.1f}m, {room.area_sqm:.1f} sqm, "
        f"ceiling {room.ceiling_height_m:.1f}m",
        f"  {len(walls)} walls; {doors} door(s), {windows} window(s)",
    ]
    if notes:
        lines.append(f"  notes: {'; '.join(notes)}")
    return "\n".join(lines)
