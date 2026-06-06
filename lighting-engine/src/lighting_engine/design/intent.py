"""LLM-2 lighting-intent schema for one room.

Per spec §4: a `RoomDesign` is a flat list of `LightingZone` entries. Each
zone explicitly names WHICH feature it lights (`target_feature_ref`,
resolved against the matching `RoomScene`) and WHY (`rationale`), so the
deterministic placement rule library can decide HOW to place fixtures
without re-asking the LLM. Inter-zone coherence is the design LLM's job at
design time — at placement time each zone is independent.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LightingIntent = Literal[
    # ceiling-driven ambient
    "cove_uplight", "level_change_uplight", "fluted_grazing",
    "perimeter_ambient", "central_ambient",
    # bed-specific
    "bedside_reading", "headboard_wash",
    # tv
    "tv_backlight",
    # accent
    "accent_artwork", "accent_niche", "accent_mirror",
    # task
    "task_dining", "task_kitchen", "task_desk", "task_vanity",
    # decorative
    "decorative_chandelier", "decorative_pendant", "decorative_floor_lamp",
]


class LightingZone(BaseModel):
    """One design intent tied to a specific feature in the room.

    Per the founder rule (`feedback_no_unjustified_heuristics.md`): every
    zone explicitly names WHICH feature it's lighting (`target_feature_ref`)
    and WHY (`rationale`). The placement rule library uses the intent to
    decide HOW to place fixtures.
    """
    model_config = ConfigDict(frozen=True)

    intent: LightingIntent
    target_feature_ref: str = Field(
        min_length=1,
        description=(
            "Anchored reference to the feature this zone lights. Format: "
            "'wall_<idx>' for wall-anchored intents, 'focal_<idx>' for "
            "furniture-anchored, 'ceiling_<type>' for ceiling-zone-anchored. "
            "Resolved by the placement rule against the RoomScene."
        ),
    )
    fixture_archetype: str = Field(
        min_length=1,
        description='"strip" | "downlight" | "pendant" | "wall_sconce" | "spotlight" | ...',
    )
    cct_k: int = Field(ge=1800, le=6500)
    cri_min: int = Field(ge=70, le=100)
    beam_deg: int | None = Field(default=None, ge=0, le=180)
    target_lux: float | None = Field(default=None, ge=0.0)
    rationale: str = Field(min_length=1)


class RoomDesign(BaseModel):
    """Output of LLM-2 — the complete lighting design for one room.

    The design is a flat list of zones. Each zone is independent at the
    placement layer (its rule places fixtures without knowing about other
    zones). Inter-zone coherence is the LLM-2's job at design time.
    """
    model_config = ConfigDict(frozen=True)

    zones: list[LightingZone] = Field(default_factory=list[LightingZone])
    overall_rationale: str = Field(
        min_length=1,
        description="2-3 sentence narrative explaining the layered approach for THIS room.",
    )
