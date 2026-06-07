"""Tests for intent_generator — mocked Anthropic client."""

from unittest.mock import MagicMock

from lighting_engine.brief.models import (
    DesignerBrief,
    FixtureCatalogOption,
    StandardsSnapshot,
)
from lighting_engine.design.intent import LightingZone, RoomDesign
from lighting_engine.design.intent_generator import (
    _format_user_message,
    generate_design,
)
from lighting_engine.design.scene import (
    CeilingZone,
    FocalPoint,
    RoomScene,
    WallPurpose,
)
from lighting_engine.models.geometry import Point


def _bedroom_scene() -> RoomScene:
    return RoomScene(
        walls=[
            WallPurpose(wall_index=0, purpose="entry", confidence=0.9),
            WallPurpose(wall_index=1, purpose="french_window", confidence=0.85),
            WallPurpose(wall_index=2, purpose="headboard", confidence=0.95),
            WallPurpose(wall_index=3, purpose="wardrobe", confidence=0.8),
        ],
        ceiling=[
            CeilingZone(type="cove", description="perimeter cove", confidence=0.85),
            CeilingZone(type="flat", description="central flat panel", confidence=0.9),
        ],
        focal_points=[FocalPoint(
            type="bed", position=Point(x=2.5, y=2),
            purpose_hint="king bed against wall C (headboard)",
        )],
        notes="Master bedroom with cove + bed against headboard wall.",
        confidence=0.88,
    )


def _brief() -> DesignerBrief:
    return DesignerBrief(
        intent_mood="wind_down",
        activities=["reading", "naps", "mood lighting"],
        time_of_use=["evening", "late_night"],
        occupants=["adult"],
    )


def _standards() -> StandardsSnapshot:
    return StandardsSnapshot(target_lux=150.0, cct_k=2700, cri_min=80)


def _catalog() -> list[FixtureCatalogOption]:
    return [FixtureCatalogOption(
        sku="strip-warm",
        name="Warm cove strip",
        wattage_w=10.0, lumens=600.0, cct_k=2700, cri=90,
        beam_angle_deg=180.0,
    )]


def test_format_user_message_includes_all_sections():
    msg = _format_user_message(
        scene=_bedroom_scene(),
        brief=_brief(),
        standards=_standards(),
        catalog=_catalog(),
        room_name="MASTER BEDROOM",
        room_type="bedroom",
    )
    assert "MASTER BEDROOM" in msg
    assert "Scene (LLM-1 output)" in msg
    assert "Designer brief" in msg
    assert "Standards" in msg
    assert "Fixture catalog" in msg
    assert "headboard" in msg
    assert "wind_down" in msg


def test_format_user_message_handles_empty_catalog():
    msg = _format_user_message(
        scene=_bedroom_scene(), brief=_brief(), standards=_standards(),
        catalog=[],
        room_name="MASTER BEDROOM", room_type="bedroom",
    )
    assert "no catalog passed" in msg


def test_generate_design_calls_claude_with_correct_params():
    expected_design = RoomDesign(
        zones=[
            LightingZone(
                intent="cove_uplight",
                target_feature_ref="ceiling_cove",
                fixture_archetype="strip", cct_k=2700, cri_min=90,
                rationale="Cove uplight for ambient wash.",
            ),
            LightingZone(
                intent="bedside_reading",
                target_feature_ref="focal_0",
                fixture_archetype="wall_sconce", cct_k=2700, cri_min=90,
                rationale="Reading sconces flanking the bed.",
            ),
        ],
        overall_rationale=(
            "Layered warm scheme — ambient from the cove pocket, task from "
            "bedside sconces, no central downlights over the bed."
        ),
    )

    fake_response = MagicMock()
    fake_response.parsed_output = expected_design
    fake_client = MagicMock()
    fake_client.messages.parse.return_value = fake_response

    result = generate_design(
        scene=_bedroom_scene(),
        brief=_brief(),
        standards=_standards(),
        catalog=_catalog(),
        room_name="MASTER BEDROOM",
        room_type="bedroom",
        client=fake_client,
    )
    assert result == expected_design

    call_kwargs = fake_client.messages.parse.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-7"
    assert call_kwargs["thinking"] == {"type": "adaptive"}
    assert call_kwargs["output_format"] is RoomDesign
    assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
