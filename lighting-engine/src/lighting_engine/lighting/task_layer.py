"""Task-layer placement: place a single focused fixture at a TargetRegion centre.

A task fixture lights an activity zone — a pendant over the dining table, a
downlight over the kitchen sink, a sconce by a bedside. The brief Zone's
position_hint resolves to a TargetRegion via the interpreter; we place one
fixture at that region's centre.
"""

from lighting_engine.brief.models import Zone
from lighting_engine.digest import RoomDigest
from lighting_engine.lighting.zone_interpreter import interpret_position_hint
from lighting_engine.models.geometry import (
    Fixture,
    FixtureSource,
    LightingLayer,
    Room,
)

# Fixture archetypes we honour as-is on the task layer. Anything else (e.g. a
# wall_washer or chandelier landing on task) is normalised to "downlight" so
# the renderer / lux model never sees a surprise type.
_VALID_TASK_FIXTURE_TYPES = frozenset({"pendant", "downlight", "spotlight"})

# Generic task-layer photometric defaults. The brief picks the archetype; the
# placement engine picks the numbers. A future revision should look these up
# from the fixture catalogue, but for v1 a single sane default per layer keeps
# the lux model deterministic.
_TASK_WATTAGE_W = 15.0
_TASK_LUMENS = 1500.0
_TASK_NARROW_BEAM_DEG = 30.0
_TASK_WIDE_BEAM_DEG = 60.0


def compute_task_layer(
    room: Room,
    digest: RoomDigest,
    zone: Zone,
) -> list[Fixture]:
    """Place a single task fixture at the zone's resolved target centre.

    Unknown fixture types collapse to "downlight" with a note in `reasoning`
    so the report shows the substitution.
    """
    target = interpret_position_hint(zone.position_hint, room, digest)
    requested = zone.fixture_type
    if requested in _VALID_TASK_FIXTURE_TYPES:
        fixture_type = requested
        type_note = ""
    else:
        fixture_type = "downlight"
        type_note = f" (substituted downlight for unsupported {requested!r})"

    fallback_note = (
        f" (fallback: {target.fallback_reason})" if target.fallback_reason else ""
    )
    reasoning = (
        f"Task layer: {zone.purpose}. {fixture_type} placed at hint "
        f"{zone.position_hint!r}"
        f"{type_note}{fallback_note}"
    )

    beam = (
        _TASK_NARROW_BEAM_DEG
        if fixture_type in ("pendant", "spotlight")
        else _TASK_WIDE_BEAM_DEG
    )
    return [
        Fixture(
            id=f"{room.id}-task-001",
            type=fixture_type,
            position=target.center,
            mount_height_m=None,
            source=FixtureSource.proposed,
            layer=LightingLayer.task,
            reasoning=reasoning,
            wattage_w=_TASK_WATTAGE_W,
            lumens=_TASK_LUMENS,
            cct_k=zone.cct_k,
            cri=zone.cri_min,
            beam_angle_deg=beam,
        )
    ]
