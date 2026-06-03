"""LLM brief layer — Step 5 of the engine pipeline.

Takes a RoomDigest + ConfirmedRoom (the user's clarifications) and asks
Claude Opus 4.7 for a structured `RoomBrief`: target lux, layered zones,
warnings, and a designer-facing rationale. The deterministic placement
code (Step 4 extensions) translates each `Zone` into fixture coordinates.

Public API:
    generate_room_brief(brief_input) -> RoomBrief
"""

from lighting_engine.brief.generator import generate_room_brief
from lighting_engine.brief.models import (
    BriefInput,
    ConfirmedRoomInput,
    DesignerBrief,
    FixtureCatalogOption,
    FixturePreference,
    LightingLayer,
    RoomBrief,
    StandardsSnapshot,
    Zone,
)

__all__ = [
    "BriefInput",
    "ConfirmedRoomInput",
    "DesignerBrief",
    "FixtureCatalogOption",
    "FixturePreference",
    "LightingLayer",
    "RoomBrief",
    "StandardsSnapshot",
    "Zone",
    "generate_room_brief",
]
