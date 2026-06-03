"""Decorative-layer placement: a statement fixture per zone (chandelier, feature pendant).

Always a single fixture at the TargetRegion centre. Decorative fixtures are
larger and brighter than task/accent (3000 lm typical), and almost always
ceiling-mounted at the room's visual centre.
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

# Decorative defaults: statement piece, broad spread.
_DECORATIVE_WATTAGE_W = 45.0
_DECORATIVE_LUMENS = 3000.0
_DECORATIVE_BEAM_DEG = 120.0
_DECORATIVE_FALLBACK_TYPE = "chandelier"


def compute_decorative_layer(
    room: Room,
    digest: RoomDigest,
    zone: Zone,
) -> list[Fixture]:
    """Place one decorative fixture at the zone's resolved target centre."""
    target = interpret_position_hint(zone.position_hint, room, digest)
    fixture_type = zone.fixture_type or _DECORATIVE_FALLBACK_TYPE
    fallback_note = (
        f" (fallback: {target.fallback_reason})" if target.fallback_reason else ""
    )
    reasoning = (
        f"Decorative layer: {zone.purpose}. {fixture_type} placed at "
        f"{zone.position_hint!r}{fallback_note}"
    )
    return [
        Fixture(
            id=f"{room.id}-dec-001",
            type=fixture_type,
            position=target.center,
            mount_height_m=None,
            source=FixtureSource.proposed,
            layer=LightingLayer.decorative,
            reasoning=reasoning,
            wattage_w=_DECORATIVE_WATTAGE_W,
            lumens=_DECORATIVE_LUMENS,
            cct_k=zone.cct_k,
            cri=zone.cri_min,
            beam_angle_deg=_DECORATIVE_BEAM_DEG,
        )
    ]
