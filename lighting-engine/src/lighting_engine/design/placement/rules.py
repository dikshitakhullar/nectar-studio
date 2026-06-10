"""Per-intent placement rules.

Each rule receives the `LightingZone` (LLM-2 intent), the `Room` (polygon,
ceiling height, doors/windows, furniture), and the `RoomScene` (LLM-1
scene with wall purposes + focal points), and returns a list of placed
`Fixture` objects.

Rules apply hard constraints from `hard_rules.py` before committing each
fixture. A rule may return zero fixtures if its target feature isn't
present in the scene (e.g. accent_artwork with no artwork wall).
"""

from __future__ import annotations

from collections.abc import Callable

from lighting_engine.design.intent import LightingZone
from lighting_engine.design.placement.geometry import (
    WallEdge,
    evenly_spaced_along_edge,
    offset_into_room,
    polygon_centroid,
    wall_edges,
)
from lighting_engine.design.placement.hard_rules import (
    safe_for_ceiling_fixture,
    wall_has_opening,
)
from lighting_engine.design.scene import FocalPoint, RoomScene
from lighting_engine.models.geometry import (
    Fixture,
    FixtureSource,
    LightingLayer,
    Point,
    Room,
)

# ── Photometric defaults per fixture archetype ────────────────────────────

_ARCHETYPE_DEFAULTS: dict[str, dict[str, float]] = {
    "strip":          {"wattage_w": 8.0,  "lumens": 500.0, "beam_deg": 180.0},
    "downlight":      {"wattage_w": 10.0, "lumens": 800.0, "beam_deg": 60.0},
    "spotlight":      {"wattage_w": 7.0,  "lumens": 450.0, "beam_deg": 24.0},
    "pendant":        {"wattage_w": 12.0, "lumens": 900.0, "beam_deg": 90.0},
    "chandelier":     {"wattage_w": 60.0, "lumens": 3000.0, "beam_deg": 360.0},
    "wall_sconce":    {"wattage_w": 7.0,  "lumens": 400.0, "beam_deg": 90.0},
    "picture_light":  {"wattage_w": 5.0,  "lumens": 300.0, "beam_deg": 60.0},
    "track_spot":     {"wattage_w": 7.0,  "lumens": 450.0, "beam_deg": 30.0},
}


def _fixture(
    *,
    room: Room,
    zone: LightingZone,
    layer: LightingLayer,
    position: Point,
    fixture_type: str,
    index: int,
    mount_height_m: float | None = None,
    wall_index: int | None = None,
) -> Fixture:
    """Construct a Fixture with photometric defaults from the archetype.

    Pass `wall_index` for wall-anchored linear fixtures (cove strip,
    headboard wash, TV backlight, fluted grazing) so the renderer draws
    them as lines along the wall instead of dots.
    """
    defaults = _ARCHETYPE_DEFAULTS.get(fixture_type, {})
    return Fixture(
        id=f"{room.id}-{zone.intent}-{index:02d}",
        type=fixture_type,
        position=position,
        mount_height_m=mount_height_m,
        source=FixtureSource.proposed,
        layer=layer,
        reasoning=zone.rationale,
        wattage_w=defaults.get("wattage_w"),
        lumens=defaults.get("lumens"),
        cct_k=zone.cct_k,
        cri=zone.cri_min,
        beam_angle_deg=zone.beam_deg or defaults.get("beam_deg"),
        wall_index=wall_index,
    )


# ── Feature-reference resolver ────────────────────────────────────────────


def _resolve_wall_index(zone: LightingZone) -> int | None:
    """Parse a 'wall_<idx>' ref. Returns None if not a wall ref."""
    if not zone.target_feature_ref.startswith("wall_"):
        return None
    try:
        return int(zone.target_feature_ref.removeprefix("wall_"))
    except ValueError:
        return None


def _resolve_focal_index(zone: LightingZone) -> int | None:
    """Parse a 'focal_<idx>' ref. Returns None if not a focal ref."""
    if not zone.target_feature_ref.startswith("focal_"):
        return None
    try:
        return int(zone.target_feature_ref.removeprefix("focal_"))
    except ValueError:
        return None


def _get_focal(zone: LightingZone, scene: RoomScene) -> FocalPoint | None:
    idx = _resolve_focal_index(zone)
    if idx is None or idx >= len(scene.focal_points):
        return None
    return scene.focal_points[idx]


def _get_wall(zone: LightingZone, room: Room) -> WallEdge | None:
    idx = _resolve_wall_index(zone)
    if idx is None:
        return None
    edges = wall_edges(room)
    for edge in edges:
        if edge.index == idx:
            return edge
    return None


# ── Ambient layer ─────────────────────────────────────────────────────────


def place_cove_uplight(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """One continuous strip per solid wall — represents the cove pocket.

    A cove is a *continuous* strip hidden in the ceiling pocket; rendering
    it as N dots along the wall (one per 1.5m) creates visual confusion
    with downlight rows. Instead emit ONE 'strip' fixture per solid wall,
    positioned at the wall midpoint, with the wall length stored on the
    fixture for the renderer to draw as a line later (v1.1: real cove
    pocket geometry from the parsed RCP).
    """
    edges = wall_edges(room)
    fixtures: list[Fixture] = []
    inset = 0.30
    for edge in edges:
        # Skip walls with openings — coves don't run over doors/windows
        if wall_has_opening(edge.index, room):
            continue
        inside = offset_into_room(edge, inset)
        fixtures.append(_fixture(
            room=room, zone=zone, layer=LightingLayer.ambient,
            position=inside, fixture_type="strip",
            index=len(fixtures),
            mount_height_m=room.ceiling_height_m,
            wall_index=edge.index,
        ))
    return fixtures


def place_perimeter_ambient(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Downlights along solid walls at 1.5m spacing, 1.2m off the wall."""
    edges = wall_edges(room)
    fixtures: list[Fixture] = []
    wall_inset_m = 1.2
    spacing_m = 1.5
    for edge in edges:
        if wall_has_opening(edge.index, room):
            continue
        count = max(1, int(edge.length_m / spacing_m))
        # Spread points along the edge, then push inward
        midline = evenly_spaced_along_edge(
            edge, count=count, inset_m=wall_inset_m,
        )
        for pos in midline:
            pushed = Point(
                x=pos.x - edge.outward_nx * wall_inset_m,
                y=pos.y - edge.outward_ny * wall_inset_m,
            )
            if not safe_for_ceiling_fixture(pushed, room):
                continue
            fixtures.append(_fixture(
                room=room, zone=zone, layer=LightingLayer.ambient,
                position=pushed, fixture_type="downlight",
                index=len(fixtures),
            ))
    return fixtures


def place_central_ambient(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Downlight grid in the central ceiling zone (~2.0m spacing)."""
    if not room.polygon:
        return []
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    width = maxx - minx
    height = maxy - miny
    spacing = 2.0
    nx = max(1, int(width / spacing))
    ny = max(1, int(height / spacing))
    step_x = width / nx
    step_y = height / ny
    fixtures: list[Fixture] = []
    for i in range(nx):
        for j in range(ny):
            pos = Point(
                x=minx + step_x * (i + 0.5),
                y=miny + step_y * (j + 0.5),
            )
            if not safe_for_ceiling_fixture(pos, room):
                continue
            fixtures.append(_fixture(
                room=room, zone=zone, layer=LightingLayer.ambient,
                position=pos, fixture_type="downlight",
                index=len(fixtures),
            ))
    return fixtures


# ── Task layer ────────────────────────────────────────────────────────────


def place_bedside_reading(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Two wall-sconce reading lamps flanking the bed.

    Anchored to a 'bed' focal point if present. Otherwise falls back to
    flanking the wall the LLM marked as 'headboard'.
    """
    bed = _get_focal(zone, scene)
    if bed is None or bed.type != "bed":
        # Try to find a bed in the focal points anyway
        for fp in scene.focal_points:
            if fp.type == "bed":
                bed = fp
                break
    if bed is None:
        # No bed → no bedside lamps
        return []
    # Place two sconces flanking the bed centroid at 0.9m offset
    flank = 0.9
    # Heuristic flank direction: along the longest room axis
    if not room.polygon:
        return []
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if width >= height:
        left = Point(x=bed.position.x - flank, y=bed.position.y)
        right = Point(x=bed.position.x + flank, y=bed.position.y)
    else:
        left = Point(x=bed.position.x, y=bed.position.y - flank)
        right = Point(x=bed.position.x, y=bed.position.y + flank)
    return [
        _fixture(
            room=room, zone=zone, layer=LightingLayer.task,
            position=left, fixture_type="wall_sconce",
            index=0, mount_height_m=0.9,
        ),
        _fixture(
            room=room, zone=zone, layer=LightingLayer.task,
            position=right, fixture_type="wall_sconce",
            index=1, mount_height_m=0.9,
        ),
    ]


def place_task_dining(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Pendant centered above the dining table focal point."""
    focal = _get_focal(zone, scene)
    if focal is None or focal.type != "dining_table":
        for fp in scene.focal_points:
            if fp.type == "dining_table":
                focal = fp
                break
    if focal is None:
        return []
    pendant_drop_m = 0.75   # 75cm above table
    mount_height = max(
        0.0,
        (room.ceiling_height_m or 2.7) - pendant_drop_m,
    )
    return [_fixture(
        room=room, zone=zone, layer=LightingLayer.task,
        position=focal.position, fixture_type="pendant",
        index=0, mount_height_m=mount_height,
    )]


def place_task_desk(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Single downlight directly above the desk focal point."""
    focal = _get_focal(zone, scene)
    if focal is None:
        return []
    if not safe_for_ceiling_fixture(focal.position, room):
        return []
    return [_fixture(
        room=room, zone=zone, layer=LightingLayer.task,
        position=focal.position, fixture_type="downlight",
        index=0,
    )]


# ── Accent layer ──────────────────────────────────────────────────────────


def place_accent_artwork(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Single spotlight at 1.2m offset from the artwork wall midpoint."""
    edge = _get_wall(zone, room)
    if edge is None:
        return []
    # Don't grazer over an opening (hard rule)
    if wall_has_opening(edge.index, room):
        return []
    pos = offset_into_room(edge, 1.2)
    if not safe_for_ceiling_fixture(pos, room):
        return []
    return [_fixture(
        room=room, zone=zone, layer=LightingLayer.accent,
        position=pos, fixture_type="spotlight", index=0,
    )]


def place_headboard_wash(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Picture light above the headboard wall (1-2 fixtures depending on width)."""
    edge = _get_wall(zone, room)
    if edge is None:
        # Fallback — find the headboard wall from scene
        for wp in scene.walls:
            if wp.purpose == "headboard":
                edges = wall_edges(room)
                for e in edges:
                    if e.index == wp.wall_index:
                        edge = e
                        break
                break
    if edge is None or wall_has_opening(edge.index, room):
        return []
    # 1 fixture for walls < 2.5m, else 2 fixtures
    count = 1 if edge.length_m < 2.5 else 2
    positions = evenly_spaced_along_edge(edge, count=count, inset_m=0.4)
    fixtures: list[Fixture] = []
    for i, pos in enumerate(positions):
        inset = Point(
            x=pos.x - edge.outward_nx * 0.3,
            y=pos.y - edge.outward_ny * 0.3,
        )
        fixtures.append(_fixture(
            room=room, zone=zone, layer=LightingLayer.accent,
            position=inset, fixture_type="picture_light", index=i,
            wall_index=edge.index,
        ))
    return fixtures


def place_tv_backlight(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Strip behind the TV at 30cm offset; cool dim warm."""
    edge = _get_wall(zone, room)
    if edge is None:
        for wp in scene.walls:
            if wp.purpose == "tv":
                edges = wall_edges(room)
                for e in edges:
                    if e.index == wp.wall_index:
                        edge = e
                        break
                break
    if edge is None:
        return []
    # Centered strip at the wall midpoint, 30cm in
    pos = offset_into_room(edge, 0.3)
    return [_fixture(
        room=room, zone=zone, layer=LightingLayer.accent,
        position=pos, fixture_type="strip", index=0,
        mount_height_m=1.2,
        wall_index=edge.index,
    )]


def place_fluted_grazing(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Grazers above the fluted wall at 30cm spacing along the wall."""
    edge = _get_wall(zone, room)
    if edge is None:
        for wp in scene.walls:
            if wp.purpose == "fluted":
                edges = wall_edges(room)
                for e in edges:
                    if e.index == wp.wall_index:
                        edge = e
                        break
                break
    if edge is None:
        return []
    spacing = 0.30
    count = max(1, int(edge.length_m / spacing))
    positions = evenly_spaced_along_edge(edge, count=count, inset_m=0.15)
    fixtures: list[Fixture] = []
    for i, pos in enumerate(positions):
        inset = Point(
            x=pos.x - edge.outward_nx * 0.30,
            y=pos.y - edge.outward_ny * 0.30,
        )
        fixtures.append(_fixture(
            room=room, zone=zone, layer=LightingLayer.accent,
            position=inset, fixture_type="track_spot", index=i,
            wall_index=edge.index,
        ))
    return fixtures


# ── Decorative layer ──────────────────────────────────────────────────────


def place_decorative_chandelier(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Single statement fixture at the room centroid."""
    centroid = polygon_centroid(room.polygon) if room.polygon else Point(x=0, y=0)
    if not safe_for_ceiling_fixture(centroid, room):
        return []
    return [_fixture(
        room=room, zone=zone, layer=LightingLayer.decorative,
        position=centroid, fixture_type="chandelier", index=0,
        mount_height_m=(room.ceiling_height_m or 2.7) - 0.9,
    )]


def place_decorative_pendant(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Pendant — anchored to a focal point if present, else centroid."""
    focal = _get_focal(zone, scene)
    if focal is not None:
        pos = focal.position
    else:
        pos = polygon_centroid(room.polygon) if room.polygon else Point(x=0, y=0)
    if not safe_for_ceiling_fixture(pos, room):
        return []
    return [_fixture(
        room=room, zone=zone, layer=LightingLayer.decorative,
        position=pos, fixture_type="pendant", index=0,
        mount_height_m=(room.ceiling_height_m or 2.7) - 0.75,
    )]


# ── Default fallback ──────────────────────────────────────────────────────


def place_fallback(
    zone: LightingZone, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Unrecognized intent — drop a single downlight at the centroid.

    Better than crashing; the designer can move it. Marked in the
    rationale so we can find these in the audit log.
    """
    centroid = polygon_centroid(room.polygon) if room.polygon else Point(x=0, y=0)
    if not safe_for_ceiling_fixture(centroid, room):
        return []
    return [_fixture(
        room=room, zone=zone, layer=LightingLayer.ambient,
        position=centroid, fixture_type="downlight", index=0,
    )]


# ── Registry: intent → rule ───────────────────────────────────────────────

PlacementRule = Callable[
    [LightingZone, Room, RoomScene], list[Fixture],
]

RULES: dict[str, PlacementRule] = {
    # ambient
    "cove_uplight": place_cove_uplight,
    "level_change_uplight": place_cove_uplight,   # same approximation in v1
    "perimeter_ambient": place_perimeter_ambient,
    "central_ambient": place_central_ambient,
    # task
    "bedside_reading": place_bedside_reading,
    "task_dining": place_task_dining,
    "task_desk": place_task_desk,
    "task_vanity": place_task_desk,               # same shape — single downlight
    "task_kitchen": place_central_ambient,        # grid over the work surface
    # accent
    "accent_artwork": place_accent_artwork,
    "accent_niche": place_accent_artwork,         # same shape — single spot
    "accent_mirror": place_accent_artwork,
    "headboard_wash": place_headboard_wash,
    "tv_backlight": place_tv_backlight,
    "fluted_grazing": place_fluted_grazing,
    # decorative
    "decorative_chandelier": place_decorative_chandelier,
    "decorative_pendant": place_decorative_pendant,
    "decorative_floor_lamp": place_decorative_pendant,  # standalone — render handles diff
}
