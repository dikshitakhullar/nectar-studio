"""Live API test for the brief generator.

Gated on the ANTHROPIC_API_KEY environment variable; SKIPPED in CI by
default. Run locally to verify the cache write/read behavior and to sanity
-check the structural shape of a real RoomBrief from Opus 4.7.
"""

import os

import anthropic
import pytest

from lighting_engine.brief import generate_room_brief
from lighting_engine.brief.models import (
    BriefInput,
    ConfirmedRoomInput,
    DesignerBrief,
    FixtureCatalogOption,
    LightingLayer,
    StandardsSnapshot,
)
from lighting_engine.digest.models import (
    OpeningOnWall,
    RoomDigest,
    WallOrientation,
    WallSegment,
)
from lighting_engine.models.geometry import Point, RoomType

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — live test skipped",
)


def _dining_room_brief_input() -> BriefInput:
    """Synthetic but plausible dining-room context."""
    digest = RoomDigest(
        room_id="r1",
        name="Dining",
        type=RoomType.dining,
        floor_level=0,
        area_sqm=18.0,
        bbox_w_m=4.5,
        bbox_h_m=4.0,
        aspect_ratio=1.125,
        ceiling_height_m=3.0,
        walls=[
            WallSegment(
                index=0,
                orientation=WallOrientation.S,
                length_m=4.5,
                start=Point(x=0, y=0),
                end=Point(x=4.5, y=0),
            ),
            WallSegment(
                index=1,
                orientation=WallOrientation.E,
                length_m=4.0,
                start=Point(x=4.5, y=0),
                end=Point(x=4.5, y=4.0),
            ),
            WallSegment(
                index=2,
                orientation=WallOrientation.N,
                length_m=4.5,
                start=Point(x=4.5, y=4.0),
                end=Point(x=0, y=4.0),
            ),
            WallSegment(
                index=3,
                orientation=WallOrientation.W,
                length_m=4.0,
                start=Point(x=0, y=4.0),
                end=Point(x=0, y=0),
            ),
        ],
        openings=[
            OpeningOnWall(
                kind="window",
                id="w1",
                wall_index=2,
                along_wall=0.5,
                width_m=1.8,
            ),
            OpeningOnWall(
                kind="door",
                id="d1",
                wall_index=0,
                along_wall=0.2,
                width_m=0.9,
            ),
        ],
        furniture_count=2,
        existing_fixture_count=0,
        notes=["N-facing window provides daylight."],
        summary=(
            "Dining room ~18 sqm, 3m ceiling, N-facing window 1.8m wide, "
            "door on S wall. Includes a dining table and chairs."
        ),
    )
    return BriefInput(
        digest=digest,
        confirmed_room=ConfirmedRoomInput(
            ceiling_type="flat",
            main_window_orientation="N",
            designer_brief=DesignerBrief(
                intent_mood="entertain",
                activities=["dining", "conversation", "evening hosting"],
                time_of_use=["evening"],
                occupants=["adult"],
                floor_finish="mid",
                wall_finish="light",
                notes="Designer wants a single statement pendant over the table.",
            ),
        ),
        standards=StandardsSnapshot(
            target_lux=200,
            cct_k=2700,
            cri_min=90,
        ),
        fixture_catalog=[
            FixtureCatalogOption(
                sku="GEN-DL-12-2700",
                name="12W warm downlight",
                wattage_w=12.0,
                lumens=1500.0,
                cct_k=2700,
                cri=90,
                beam_angle_deg=60.0,
            ),
            FixtureCatalogOption(
                sku="GEN-DL-12-4000",
                name="12W cool downlight",
                wattage_w=12.0,
                lumens=1500.0,
                cct_k=4000,
                cri=90,
                beam_angle_deg=60.0,
            ),
        ],
    )


def test_live_dining_room_brief_is_structurally_valid():
    """One real round-trip against Opus 4.7 — basic structural assertions."""
    client = anthropic.Anthropic()
    brief = generate_room_brief(_dining_room_brief_input(), client=client)

    # Structural — these are the floor; the model is free to vary specifics.
    assert brief.target_lux_ambient > 0
    assert 2200 <= brief.cct_main <= 4000
    assert len(brief.zones) >= 1
    assert any(z.layer == LightingLayer.ambient for z in brief.zones), (
        "RoomBrief must include at least one ambient zone"
    )
    assert brief.design_rationale, "design_rationale should not be empty"
    # Dining is warm-bias by default.
    assert brief.fixture_preference.value in {"warm-bias", "mixed"}
