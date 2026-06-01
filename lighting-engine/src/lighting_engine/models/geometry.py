"""Canonical geometric IR for a parsed residential plan.

Units throughout this module are SI (meters) and degrees. Coordinates are in a
plan-local frame whose origin is the bottom-left of the detected plan region.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class Point(BaseModel):
    model_config = ConfigDict(frozen=True)
    x: float
    y: float


class RoomType(str, Enum):
    living = "living"
    dining = "dining"
    bedroom = "bedroom"
    kitchen = "kitchen"
    bathroom = "bathroom"
    study = "study"
    hallway = "hallway"
    staircase = "staircase"
    foyer = "foyer"
    outdoor = "outdoor"
    unknown = "unknown"


class DoorSwing(str, Enum):
    in_ = "in"
    out = "out"
    sliding = "sliding"
    unknown = "unknown"


class Window(BaseModel):
    id: str
    wall_index: int                # index into Room.polygon edge list
    along_wall: float = Field(ge=0.0, le=1.0)  # fraction along that wall
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    sill_height_m: float = Field(ge=0)
    is_glazed_door: bool = False   # balcony-doors classified as windows for daylight


class Door(BaseModel):
    id: str
    wall_index: int
    along_wall: float = Field(ge=0.0, le=1.0)
    width_m: float = Field(gt=0)
    swing: DoorSwing = DoorSwing.unknown


class Furniture(BaseModel):
    id: str
    raw_label: str | None = None   # "FRIDGE", "sofa 053", block name, etc.
    type: str = "unknown"          # designer batch-tags this later
    position: Point
    footprint: list[Point] = Field(default_factory=list)  # may be empty


class Fixture(BaseModel):
    id: str
    raw_label: str | None = None
    type: str = "unknown"
    position: Point
    mount_height_m: float | None = None  # None = ceiling-mounted


class CeilingFeature(BaseModel):
    id: str
    kind: str                       # "beam" | "soffit" | "cove" | "height_change" | "skylight"
    polygon: list[Point]
    depth_m: float = 0.0


class Room(BaseModel):
    id: str
    name: str
    type: RoomType = RoomType.unknown
    polygon: list[Point]
    ceiling_height_m: float = Field(gt=0)
    windows: list[Window] = Field(default_factory=list)
    doors: list[Door] = Field(default_factory=list)
    furniture: list[Furniture] = Field(default_factory=list)
    ceiling_features: list[CeilingFeature] = Field(default_factory=list)
    existing_fixtures: list[Fixture] = Field(default_factory=list)

    @field_validator("polygon")
    @classmethod
    def _polygon_has_three_points(cls, v: list[Point]) -> list[Point]:
        if len(v) < 3:
            raise ValueError("polygon needs at least 3 points")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def area_sqm(self) -> float:
        # Shoelace formula
        n = len(self.polygon)
        s = 0.0
        for i in range(n):
            x1, y1 = self.polygon[i].x, self.polygon[i].y
            x2, y2 = self.polygon[(i + 1) % n].x, self.polygon[(i + 1) % n].y
            s += x1 * y2 - x2 * y1
        return abs(s) / 2.0


class Project(BaseModel):
    id: str
    name: str
    location: str = "delhi"
    floor_level: int = 0
    north_orientation_deg: float = 0.0
    rooms: list[Room] = Field(default_factory=list)
