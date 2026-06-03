"""RoomBrief schema + brief-input schema for the LLM brief layer.

Design spec §4.1: the LLM emits **semantic zones** — never coordinates. The
deterministic placement code (Step 4 extensions) translates each zone into
actual fixture positions on the room polygon.

This module deliberately re-defines `LightingLayer` so the brief package is
self-contained for downstream consumers (placement, render) and so the
RoomBrief JSON schema is generatable from this file alone — important
because the schema is embedded in the cached system prompt.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lighting_engine.digest.models import RoomDigest


class LightingLayer(StrEnum):
    """Layered-lighting role of a zone (residential design convention).

    Mirrors `lighting_engine.models.geometry.LightingLayer` — the brief
    package owns its own definition so the package is import-self-contained.
    """
    ambient = "ambient"
    task = "task"
    accent = "accent"
    decorative = "decorative"


class FixturePreference(StrEnum):
    """Bias for the overall room palette — read by placement code."""
    warm_bias = "warm-bias"
    cool_bias = "cool-bias"
    mixed = "mixed"


class Zone(BaseModel):
    """A single lighting zone — one row in the layered lighting plan.

    `position_hint` is a free-text spatial cue that the deterministic
    placement engine resolves against the room polygon + digest's
    furniture and openings (e.g. "above dining table" → look up the
    dining table furniture entry's centroid).
    """
    model_config = ConfigDict(extra="forbid")

    layer: LightingLayer = Field(
        description="Which functional layer this zone serves.",
    )
    purpose: str = Field(
        min_length=1,
        description="Short human-readable reason. E.g. 'ambient wash over seating' "
                    "or 'task light over dining table'.",
    )
    cct_k: int = Field(
        ge=1800,
        le=6500,
        description="Color temperature for this zone, in Kelvin. "
                    "Warm 2700-3000K for living/dining/bedroom; cool 3500-4000K "
                    "for kitchen/bath/study task.",
    )
    cri_min: int = Field(
        ge=70,
        le=100,
        description="Minimum CRI. 90+ wherever skin or food is seen.",
    )
    fixture_type: str = Field(
        min_length=1,
        description='Fixture archetype. One of: "downlight", "pendant", "cove", '
                    '"chandelier", "sconce", "track_spot", "picture_light", '
                    '"floor_lamp", "table_lamp", "strip", "wall_washer".',
    )
    position_hint: str = Field(
        min_length=1,
        description='Spatial cue interpreted by the placement engine. E.g. '
                    '"center of ceiling", "above dining table", "wall N near window", '
                    '"flanking bed", "perimeter cove".',
    )


class RoomBrief(BaseModel):
    """Structured plan emitted by the LLM for a single confirmed room.

    Two halves:
      * Machine fields (`target_lux_ambient`, `cct_main`, `zones`, ...) drive
        deterministic placement and the lux uniformity check.
      * Text fields (`design_rationale`, `design_notes`) drive the pack's
        designer-facing narrative.
    """
    model_config = ConfigDict(extra="forbid")

    # ── machine fields → deterministic placement ──────────────────────────
    target_lux_ambient: float = Field(
        gt=0,
        description="Target ambient illuminance on the work plane (lux). "
                    "Bounded by IS 3646 / IES residential standards for the room type, "
                    "uplifted for elderly occupants or task-heavy use.",
    )
    cct_main: int = Field(
        ge=1800,
        le=6500,
        description="Dominant CCT for the ambient layer in Kelvin.",
    )
    fixture_preference: FixturePreference = Field(
        description="Overall warm/cool bias for the room's palette.",
    )
    layers_needed: list[LightingLayer] = Field(
        min_length=1,
        description="Which functional layers the room needs. Hard rule: at minimum "
                    "an ambient layer plus one of task / accent.",
    )
    zones: list[Zone] = Field(
        min_length=1,
        description="Concrete zones for the placement engine to materialize.",
    )
    warnings: list[str] = Field(
        default_factory=list[str],
        description="Engine-readable warnings. E.g. 'no daylight side — increase "
                    "ambient' or 'low ceiling — avoid pendants'.",
    )

    # ── text fields → report rendering ────────────────────────────────────
    design_rationale: str = Field(
        min_length=1,
        description="1-3 paragraphs of designer-facing prose explaining why this "
                    "plan fits the room's purpose, occupants, and time of use. "
                    "Names the layer gap being closed.",
    )
    design_notes: list[str] = Field(
        default_factory=list[str],
        description="Bullet-style designer notes: scene programming hints, dimming "
                    "rules, fixture substitutions, things to verify on site.",
    )
    floor_lamp_suggestions: list[Zone] = Field(
        default_factory=list[Zone],
        description="Floor-lamp positions rendered on the furniture plan, not the RCP. "
                    "Use `layer: decorative` or `layer: ambient` and a "
                    "furniture-relative `position_hint`.",
    )
    table_lamp_suggestions: list[Zone] = Field(
        default_factory=list[Zone],
        description="Table-lamp positions rendered on the furniture plan. "
                    "Same shape as floor lamps; smaller, more local fill.",
    )


# ── Brief input — what the generator receives ─────────────────────────────


class FixtureCatalogOption(BaseModel):
    """A single fixture option from `lighting/fixtures.py` projected for the LLM.

    The brief only sees archetypes and key numbers — not real SKUs and not
    deterministic placement output. The model picks fixture *types* per zone;
    the placement engine then picks the actual catalog row.
    """
    model_config = ConfigDict(extra="forbid")

    sku: str
    name: str
    wattage_w: float
    lumens: float
    cct_k: int
    cri: int
    beam_angle_deg: float


class StandardsSnapshot(BaseModel):
    """The deterministic numbers the LLM must respect, in one place.

    Sourced from `lighting/standards.py`. The model uses these as a floor /
    starting point; it may justify deviations in `warnings`.
    """
    model_config = ConfigDict(extra="forbid")

    target_lux: float = Field(gt=0)
    cct_k: int = Field(ge=1800, le=6500)
    cri_min: int = Field(ge=70, le=100)


class DesignerBrief(BaseModel):
    """The designer's intent for the room (from `/studio/brief`)."""
    model_config = ConfigDict(extra="forbid")

    intent_mood: Literal["cozy", "productive", "wind_down", "entertain"] = Field(
        description="Single-word mood read of the room.",
    )
    activities: list[str] = Field(
        default_factory=list[str],
        description='Free-text activity list. E.g. ["dining", "reading", "TV"].',
    )
    time_of_use: list[Literal["morning", "evening", "late_night"]] = Field(
        default_factory=list[Literal["morning", "evening", "late_night"]],
        description="When the room is primarily used.",
    )
    occupants: list[Literal["kids", "young_adult", "adult", "elderly"]] = Field(
        default_factory=list[Literal["kids", "young_adult", "adult", "elderly"]],
        description="Who uses the room — drives lux uplift for elderly, CCT cap for kids.",
    )
    floor_finish: Literal["light", "mid", "dark"] | None = None
    wall_finish: Literal["light", "mid", "dark"] | None = None
    notes: str = Field(
        default="",
        description="Free-text designer notes that didn't fit other fields.",
    )


class ConfirmedRoomInput(BaseModel):
    """The user-confirmed room context, distilled for the brief.

    This is a thin projection of `ConfirmedRoom` (spec §3.2) — only the
    fields the LLM actually needs to reason about lighting. Geometry lives
    in the `RoomDigest`; this struct carries the clarifications.
    """
    model_config = ConfigDict(extra="forbid")

    ceiling_type: Literal["false", "flat", "sloped", "mixed"] = "flat"
    main_window_orientation: Literal["N", "S", "E", "W", "none"] = "none"
    designer_brief: DesignerBrief


class BriefInput(BaseModel):
    """Single struct passed to `generate_room_brief`.

    Bundles everything the LLM sees in the per-room user message:
      * the spatial digest (walls / openings / adjacency / daylight)
      * the user's clarifications (intent / activities / occupants)
      * the deterministic numbers (target lux, CCT, fixture catalog options)
    """
    model_config = ConfigDict(extra="forbid")

    digest: RoomDigest = Field(
        description="Resolved spatial facts for the room (walls, openings, "
                    "adjacency, daylight side).",
    )
    confirmed_room: ConfirmedRoomInput
    standards: StandardsSnapshot
    fixture_catalog: list[FixtureCatalogOption] = Field(
        default_factory=list[FixtureCatalogOption],
        description="Available fixture archetypes from `lighting/fixtures.py`.",
    )
