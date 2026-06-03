"""Walk the zones in a RoomBrief and dispatch each to its layer function.

Single entry point used by the API: given a `Room` + `RoomDigest` + `RoomBrief`,
walk every brief Zone and produce a flat `list[Fixture]`. Ambient stays on the
existing `compute_ambient_layer` (grid-based lumen method); task / accent /
decorative each have their own module. Multiple ambient zones in one brief
collapse to a single ambient grid pass — the grid is sized off room geometry,
not zone count.
"""

from lighting_engine.brief.models import LightingLayer, RoomBrief
from lighting_engine.digest import RoomDigest
from lighting_engine.lighting.accent_layer import compute_accent_layer
from lighting_engine.lighting.decorative_layer import compute_decorative_layer
from lighting_engine.lighting.placement import compute_ambient_layer
from lighting_engine.lighting.task_layer import compute_task_layer
from lighting_engine.models.geometry import Fixture, Room


def compute_all_fixtures(
    room: Room,
    digest: RoomDigest,
    brief: RoomBrief,
) -> list[Fixture]:
    """Materialise every zone in `brief` into Fixtures on the room polygon."""
    out: list[Fixture] = []
    ambient_done = False
    for zone in brief.zones:
        if zone.layer == LightingLayer.ambient:
            # Ambient uses the existing grid-based lumen method.
            # Multiple ambient zones collapse to one grid pass — the grid
            # is geometry-driven, not zone-count-driven.
            if not ambient_done:
                out.extend(compute_ambient_layer(room, digest))
                ambient_done = True
        elif zone.layer == LightingLayer.task:
            out.extend(compute_task_layer(room, digest, zone))
        elif zone.layer == LightingLayer.accent:
            out.extend(compute_accent_layer(room, digest, zone))
        elif zone.layer == LightingLayer.decorative:
            out.extend(compute_decorative_layer(room, digest, zone))
    return out
