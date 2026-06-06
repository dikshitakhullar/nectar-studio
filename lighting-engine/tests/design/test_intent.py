import pytest
from pydantic import ValidationError

from lighting_engine.design.intent import LightingZone, RoomDesign


def test_lighting_zone_round_trip():
    z = LightingZone(
        intent="bedside_reading",
        target_feature_ref="focal_0",
        fixture_archetype="wall_sconce",
        cct_k=2700, cri_min=90, beam_deg=60,
        target_lux=150.0,
        rationale="Reading lamps flanking the bed at 60cm from edges, 0.9m mount.",
    )
    assert z.intent == "bedside_reading"
    assert z.target_feature_ref == "focal_0"


def test_lighting_zone_rejects_unknown_intent():
    with pytest.raises(ValidationError):
        LightingZone(
            intent="bogus_intent",
            target_feature_ref="wall_0",
            fixture_archetype="downlight",
            cct_k=3000, cri_min=80,
            rationale="x",
        )


def test_lighting_zone_optional_beam_and_lux():
    z = LightingZone(
        intent="cove_uplight",
        target_feature_ref="ceiling_cove",
        fixture_archetype="strip",
        cct_k=3000, cri_min=80,
        beam_deg=None, target_lux=None,
        rationale="Indirect strip in the cove pocket.",
    )
    assert z.beam_deg is None
    assert z.target_lux is None


def test_lighting_zone_cct_bounds():
    with pytest.raises(ValidationError):
        LightingZone(
            intent="cove_uplight", target_feature_ref="ceiling_cove",
            fixture_archetype="strip", cct_k=10_000, cri_min=80,
            rationale="x",
        )


def test_room_design_requires_rationale():
    with pytest.raises(ValidationError):
        RoomDesign(zones=[], overall_rationale="")  # min_length=1


def test_room_design_full_round_trip():
    design = RoomDesign(
        zones=[
            LightingZone(
                intent="cove_uplight", target_feature_ref="ceiling_cove",
                fixture_archetype="strip", cct_k=3000, cri_min=80,
                rationale="Cove pocket gets a warm indirect strip.",
            ),
            LightingZone(
                intent="bedside_reading", target_feature_ref="focal_0",
                fixture_archetype="wall_sconce", cct_k=2700, cri_min=90,
                rationale="Flanking sconces for reading at the headboard.",
            ),
        ],
        overall_rationale=(
            "Layered warm scheme — ambient from the cove, task from the "
            "bedside sconces, no accent because no artwork was identified."
        ),
    )
    serialized = design.model_dump(mode="json")
    rebuilt = RoomDesign.model_validate(serialized)
    assert rebuilt == design
