"""Pydantic models for the FastAPI HTTP contract.

These are *wire* models. The domain IR lives in
``lighting_engine.models.geometry`` and is intentionally kept separate — the
domain models stay pure geometric concepts, while these models add the
clarification + provenance fields the studio frontend writes.

Spec reference: 2026-06-03-v1-design.md §3.2 (ConfirmedRoom) and §4.7
(PlanResponse).
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lighting_engine.models.geometry import (
    CeilingFeature,
    Door,
    Furniture,
    Point,
    RoomType,
    Window,
)

# ---------------------------------------------------------------------------
# Enums (clarification vocabulary; see spec §3.2)
# ---------------------------------------------------------------------------

class RoomTier(StrEnum):
    """Which tier of the room filter a parsed room falls into (spec §3.1)."""
    first_class = "first_class"
    generic = "generic"


class CeilingType(StrEnum):
    none = "none"            # exposed slab / no false ceiling
    flat = "flat"
    sloped = "sloped"
    mixed = "mixed"


class Direction(StrEnum):
    """Cardinal direction — used for main window orientation."""
    north = "N"
    south = "S"
    east = "E"
    west = "W"


class Occupant(StrEnum):
    kids = "kids"
    young_adult = "young_adult"
    adult = "adult"
    elderly = "elderly"


class FinishTone(StrEnum):
    light = "light"
    mid = "mid"
    dark = "dark"


class Mood(StrEnum):
    cozy = "cozy"
    productive = "productive"
    wind_down = "wind_down"
    entertain = "entertain"


class TimeOfDay(StrEnum):
    morning = "morning"
    evening = "evening"
    late_night = "late_night"


class JobStatusValue(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


# ---------------------------------------------------------------------------
# Room dims
# ---------------------------------------------------------------------------

class RoomDims(BaseModel):
    """Bounding-box dimensions of a room polygon."""
    model_config = ConfigDict(frozen=True)
    length_m: float = Field(gt=0)
    width_m: float = Field(gt=0)


# ---------------------------------------------------------------------------
# /api/projects — response models
# ---------------------------------------------------------------------------

class RoomSummary(BaseModel):
    """Lightweight room descriptor returned after upload / on the rooms list."""
    id: str
    name: str
    type: RoomType
    dims: RoomDims
    polygon: list[Point]
    doors: list[Door]
    windows: list[Window]
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    tier: RoomTier
    # Workflow status — set by the studio as the designer moves through screens.
    # "new" until the user touches the room; otherwise studio-defined.
    status: str = "new"


class ProjectCreateResponse(BaseModel):
    project_id: str
    rooms: list[RoomSummary]


class RoomListResponse(BaseModel):
    rooms: list[RoomSummary]


# ---------------------------------------------------------------------------
# ConfirmedRoom — the merge target written by the studio (spec §3.2)
# ---------------------------------------------------------------------------

class WallConfirmation(BaseModel):
    """Per-wall confirmation payload from /studio/walls."""
    index: int = Field(ge=0)
    confirm: bool = True
    doors_confirmed: list[Door] = Field(default_factory=list[Door])
    windows_confirmed: list[Window] = Field(default_factory=list[Window])
    notes: str = ""


class ClarificationRequest(BaseModel):
    """Body for POST /api/projects/{pid}/rooms/{rid} (the /studio/room-basics
    screen)."""
    type_confirmed: RoomType | None = None
    length_m: float | None = Field(default=None, gt=0)
    width_m: float | None = Field(default=None, gt=0)
    ceiling_height_m: float | None = Field(default=None, gt=0)
    ceiling_type: CeilingType | None = None
    main_window_orientation: Direction | None = None
    occupants: list[Occupant] | None = None
    floor_finish: FinishTone | None = None
    wall_finish: FinishTone | None = None


class FurnitureRequest(BaseModel):
    """Body for POST /api/projects/{pid}/rooms/{rid}/furniture."""
    furniture_notes: str = ""
    mood: Mood | None = None
    activities: list[str] = Field(default_factory=list[str])


class BriefRequest(BaseModel):
    """Body for POST /api/projects/{pid}/rooms/{rid}/brief."""
    intent_mood: Mood | None = None
    activities: list[str] = Field(default_factory=list[str])
    time_of_use: list[TimeOfDay] = Field(default_factory=list[TimeOfDay])
    notes: str = ""


class ConfirmedRoom(BaseModel):
    """The merge target — one blob per (project_id, room_id).

    Mirrors spec §3.2. Stored as a JSON column on the RoomRecord ORM model.
    """
    model_config = ConfigDict(populate_by_name=True)

    # --- from parser (immutable after upload) ---
    id: str
    name: str
    type_inferred: RoomType
    polygon_inferred: list[Point]
    doors_parsed: list[Door] = Field(default_factory=list[Door])
    windows_parsed: list[Window] = Field(default_factory=list[Window])
    furniture_parsed: list[Furniture] = Field(default_factory=list[Furniture])
    ceiling_features_parsed: list[CeilingFeature] = Field(
        default_factory=list[CeilingFeature]
    )
    tier: RoomTier = RoomTier.first_class

    # --- from /studio/room-basics ---
    type_confirmed: RoomType | None = None
    length_m: float | None = Field(default=None, gt=0)
    width_m: float | None = Field(default=None, gt=0)
    ceiling_height_m: float | None = Field(default=None, gt=0)
    ceiling_type: CeilingType | None = None
    main_window_orientation: Direction | None = None
    occupants: list[Occupant] = Field(default_factory=list[Occupant])
    floor_finish: FinishTone | None = None
    wall_finish: FinishTone | None = None

    # --- from /studio/walls ---
    walls: list[WallConfirmation] = Field(default_factory=list[WallConfirmation])

    # --- from /studio/furniture ---
    furniture_notes: str = ""

    # --- from /studio/brief ---
    intent_mood: Mood | None = None
    activities: list[str] = Field(default_factory=list[str])
    time_of_use: list[TimeOfDay] = Field(default_factory=list[TimeOfDay])

    # --- provenance: which fields originated from parser vs user ---
    provenance: dict[str, str] = Field(default_factory=dict[str, str])


# ---------------------------------------------------------------------------
# Generation / jobs
# ---------------------------------------------------------------------------

class GenerateResponse(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    job_id: str
    project_id: str
    room_id: str
    status: JobStatusValue
    error: str | None = None
    result_url: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PlanResponse — spec §4.7
# ---------------------------------------------------------------------------

class LuxStats(BaseModel):
    mean_lux: float
    min_lux: float
    max_lux: float
    uniformity: float
    target_lux: float
    meets_target: bool


class FixtureRow(BaseModel):
    sku: str
    name: str
    wattage_w: float
    lumens: float
    cct_k: int
    cri: int
    beam_angle_deg: float
    count: int


class PlanResponse(BaseModel):
    project_id: str
    room_id: str
    rcp_svg: str
    furniture_svg: str
    lux_uniformity: LuxStats
    fixture_schedule: list[FixtureRow]
    design_rationale: str
    design_notes: list[str]
    warnings: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


# ---------------------------------------------------------------------------
# Walls endpoint response
# ---------------------------------------------------------------------------

class WallsResponse(BaseModel):
    project_id: str
    room_id: str
    walls: list[WallConfirmation]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "lighting-engine"
    version: str
