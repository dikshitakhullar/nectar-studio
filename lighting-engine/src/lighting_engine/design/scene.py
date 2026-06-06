"""LLM-1 scene-understanding schema for one room.

Per spec §4: the scene describes WHAT'S IN this specific room so the
downstream design LLM (LLM-2) can reason contextually rather than from a
generic "bedroom" template. Every field is anchored to actual room geometry
(wall index, room-local coordinates, focal-point type) so the placement
rule library can resolve references without re-running vision.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lighting_engine.models.geometry import Point

WallPurposeLiteral = Literal[
    "headboard", "tv", "artwork", "blank", "fluted",
    "french_window", "balcony_door", "entry", "wardrobe",
    "feature_panel", "mirror", "bookshelf",
]


class WallPurpose(BaseModel):
    """One wall's design purpose, identified by LLM-1 from the rendered scene."""
    model_config = ConfigDict(frozen=True)

    wall_index: int = Field(ge=0)            # polygon edge index
    purpose: WallPurposeLiteral
    features: list[str] = Field(default_factory=list)  # Claude's observations
    confidence: float = Field(ge=0.0, le=1.0)


CeilingZoneType = Literal["cove", "flat", "level_change", "fluted", "tray"]


class CeilingZone(BaseModel):
    """One zone within the room's ceiling structure."""
    model_config = ConfigDict(frozen=True)

    type: CeilingZoneType
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


FocalPointType = Literal[
    "dining_table", "bed", "sofa", "desk",
    "vanity", "kitchen_island", "puja_altar",
]


class FocalPoint(BaseModel):
    """A specific object Claude identified as a focal element for lighting design."""
    model_config = ConfigDict(frozen=True)

    type: FocalPointType
    position: Point                          # room-local coordinates (meters)
    purpose_hint: str = Field(min_length=1)  # "head end of bed faces north"


class RoomScene(BaseModel):
    """Output of LLM-1 scene understanding for one room.

    The scene's job is to describe WHAT'S IN THIS SPECIFIC ROOM so that
    LLM-2 can design contextually rather than from a generic "bedroom"
    template. Every field is anchored to actual room geometry (wall index,
    coordinates, focal points).
    """
    model_config = ConfigDict(frozen=True)

    walls: list[WallPurpose] = Field(default_factory=list[WallPurpose])
    ceiling: list[CeilingZone] = Field(default_factory=list[CeilingZone])
    focal_points: list[FocalPoint] = Field(default_factory=list[FocalPoint])
    notes: str = ""                          # Claude's overall scene narrative
    confidence: float = Field(ge=0.0, le=1.0)
