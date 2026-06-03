"""Schema-level tests for the brief layer's pydantic models."""

import json

import pytest
from pydantic import ValidationError

from lighting_engine.brief.models import (
    FixturePreference,
    LightingLayer,
    RoomBrief,
    Zone,
)


def test_lighting_layer_enum_has_all_four_values():
    assert {layer.value for layer in LightingLayer} == {
        "ambient",
        "task",
        "accent",
        "decorative",
    }


def test_zone_round_trip_via_json():
    zone = Zone(
        layer=LightingLayer.task,
        purpose="task light above dining table",
        cct_k=2700,
        cri_min=90,
        fixture_type="pendant",
        position_hint="above dining table",
    )
    blob = zone.model_dump_json()
    restored = Zone.model_validate_json(blob)
    assert restored == zone


def test_room_brief_minimum_valid_example_round_trips():
    """Build a small but realistic RoomBrief and verify schema round-trip."""
    brief = RoomBrief(
        target_lux_ambient=150.0,
        cct_main=2700,
        fixture_preference=FixturePreference.warm_bias,
        layers_needed=[LightingLayer.ambient, LightingLayer.task, LightingLayer.accent],
        zones=[
            Zone(
                layer=LightingLayer.ambient,
                purpose="ambient downlight grid over seating",
                cct_k=2700,
                cri_min=90,
                fixture_type="downlight",
                position_hint="center of ceiling",
            ),
            Zone(
                layer=LightingLayer.task,
                purpose="task light above dining table",
                cct_k=2700,
                cri_min=90,
                fixture_type="pendant",
                position_hint="above dining table",
            ),
            Zone(
                layer=LightingLayer.accent,
                purpose="accent on artwork along long wall",
                cct_k=2700,
                cri_min=90,
                fixture_type="picture_light",
                position_hint="wall N — interior wall, likely artwork",
            ),
        ],
        warnings=["no daylight side detected — increased ambient by 30%"],
        design_rationale=(
            "This drawing-room currently has no eye-level layer. We add a warm "
            "downlight wash for ambient, a single pendant over the dining table "
            "to anchor the seating, and a picture light on the long interior "
            "wall so the eye lands on the artwork."
        ),
        design_notes=[
            "Spec dim-to-warm driver on ambient downlights.",
            "Pendant ½–⅔ table width, 30-36\" above tabletop.",
        ],
    )

    blob = brief.model_dump_json()
    parsed = RoomBrief.model_validate_json(blob)
    assert parsed == brief
    assert parsed.target_lux_ambient == 150.0
    assert parsed.zones[0].layer == LightingLayer.ambient
    assert parsed.fixture_preference == FixturePreference.warm_bias


def test_room_brief_rejects_empty_zones():
    with pytest.raises(ValidationError):
        RoomBrief(
            target_lux_ambient=150.0,
            cct_main=2700,
            fixture_preference=FixturePreference.warm_bias,
            layers_needed=[LightingLayer.ambient],
            zones=[],  # min_length=1
            design_rationale="x",
        )


def test_room_brief_rejects_invalid_cct():
    with pytest.raises(ValidationError):
        Zone(
            layer=LightingLayer.ambient,
            purpose="x",
            cct_k=10000,  # > 6500 ceiling
            cri_min=90,
            fixture_type="downlight",
            position_hint="center",
        )


def test_room_brief_rejects_zero_target_lux():
    with pytest.raises(ValidationError):
        RoomBrief(
            target_lux_ambient=0.0,  # gt=0
            cct_main=2700,
            fixture_preference=FixturePreference.warm_bias,
            layers_needed=[LightingLayer.ambient],
            zones=[
                Zone(
                    layer=LightingLayer.ambient,
                    purpose="x",
                    cct_k=2700,
                    cri_min=90,
                    fixture_type="downlight",
                    position_hint="center",
                ),
            ],
            design_rationale="x",
        )


def test_room_brief_json_schema_is_generatable():
    """The prompt embeds RoomBrief.model_json_schema() — must not raise."""
    schema = RoomBrief.model_json_schema()
    assert schema["type"] == "object"
    assert "target_lux_ambient" in schema["properties"]
    assert "zones" in schema["properties"]
    # Sanity: schema is serialisable deterministically.
    blob = json.dumps(schema, sort_keys=True)
    assert "target_lux_ambient" in blob
