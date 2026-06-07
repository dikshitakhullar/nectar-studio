"""Orchestrator — converts a RoomDesign into placed Fixtures.

Iterates each LightingZone, dispatches to the registered placement rule,
and returns the merged Fixture list. Unrecognized intents fall through to
the fallback rule (single downlight at centroid + audit note).
"""

from __future__ import annotations

from lighting_engine.design.intent import RoomDesign
from lighting_engine.design.placement.rules import RULES, place_fallback
from lighting_engine.design.scene import RoomScene
from lighting_engine.models.geometry import Fixture, Room


def place_design(
    *, design: RoomDesign, room: Room, scene: RoomScene,
) -> list[Fixture]:
    """Apply each zone's placement rule and return the merged Fixture list."""
    fixtures: list[Fixture] = []
    for zone in design.zones:
        rule = RULES.get(zone.intent, place_fallback)
        fixtures.extend(rule(zone, room, scene))
    return fixtures
