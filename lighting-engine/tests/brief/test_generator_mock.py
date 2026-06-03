"""Mocked-client test for `generate_room_brief`.

Verifies the request shape (model, thinking, output_config, system blocks
with cache_control) without touching the network. The live test
(`test_generator_live.py`) covers the real round-trip.
"""

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from lighting_engine.brief import generate_room_brief
from lighting_engine.brief.generator import MAX_OUTPUT_TOKENS, MODEL_ID
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
from lighting_engine.digest.models import (
    OpeningOnWall,
    RoomDigest,
    WallOrientation,
    WallSegment,
)
from lighting_engine.models.geometry import Point, RoomType


def _example_brief_input() -> BriefInput:
    """A synthetic dining-room brief input."""
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
        ],
        furniture_count=1,
        existing_fixture_count=0,
        summary="Dining room, ~18 sqm, N-facing window.",
    )
    return BriefInput(
        digest=digest,
        confirmed_room=ConfirmedRoomInput(
            ceiling_type="flat",
            main_window_orientation="N",
            designer_brief=DesignerBrief(
                intent_mood="entertain",
                activities=["dining", "conversation"],
                time_of_use=["evening"],
                occupants=["adult"],
                floor_finish="mid",
                wall_finish="light",
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
        ],
    )


def _example_room_brief() -> RoomBrief:
    """A realistic RoomBrief the mock will hand back."""
    return RoomBrief(
        target_lux_ambient=200.0,
        cct_main=2700,
        fixture_preference=FixturePreference.warm_bias,
        layers_needed=[LightingLayer.ambient, LightingLayer.task, LightingLayer.decorative],
        zones=[
            Zone(
                layer=LightingLayer.ambient,
                purpose="warm downlight wash over the dining area",
                cct_k=2700,
                cri_min=90,
                fixture_type="downlight",
                position_hint="center of ceiling",
            ),
            Zone(
                layer=LightingLayer.task,
                purpose="task light over dining table",
                cct_k=2700,
                cri_min=90,
                fixture_type="pendant",
                position_hint="above dining table",
            ),
        ],
        warnings=[],
        design_rationale="Single statement pendant anchors the table, soft warm wash around it.",
        design_notes=["Spec dimmer for the pendant."],
    )


def _build_mock_client(parsed: RoomBrief) -> MagicMock:
    """Construct a MagicMock that mimics `anthropic.Anthropic` for `parse`."""
    fake_message = MagicMock()
    fake_message.parsed_output = parsed
    fake_message.usage = MagicMock(
        input_tokens=42,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=5000,
        output_tokens=900,
    )

    client = MagicMock()
    client.messages.parse.return_value = fake_message
    return client


def _captured_kwargs(client: MagicMock) -> dict[str, Any]:
    """Type-erased view of the kwargs the generator passed to messages.parse."""
    call_args = client.messages.parse.call_args
    kwargs: dict[str, Any] = call_args.kwargs
    return kwargs


def test_generate_room_brief_returns_parsed_output():
    """Happy path — generator returns the mock's parsed_output verbatim."""
    expected = _example_room_brief()
    client = _build_mock_client(expected)

    result = generate_room_brief(_example_brief_input(), client=client)

    assert result == expected
    client.messages.parse.assert_called_once()


def test_generate_room_brief_uses_opus_4_7_and_adaptive_thinking():
    client = _build_mock_client(_example_room_brief())

    generate_room_brief(_example_brief_input(), client=client)

    kwargs = _captured_kwargs(client)
    assert kwargs["model"] == MODEL_ID
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["max_tokens"] == MAX_OUTPUT_TOKENS
    assert kwargs["thinking"] == {"type": "adaptive"}


def test_generate_room_brief_uses_output_config_high_effort_and_structured_format():
    client = _build_mock_client(_example_room_brief())

    generate_room_brief(_example_brief_input(), client=client)

    kwargs = _captured_kwargs(client)
    # The spec mandates `effort: "high"`. The SDK merges `output_format` into
    # `output_config.format`, so we verify the kwargs we actually pass.
    assert kwargs["output_config"] == {"effort": "high"}
    assert kwargs["output_format"] is RoomBrief


def test_generate_room_brief_does_not_pass_temperature_or_top_p_or_top_k():
    """Opus 4.7 removed these sampling params; pyright-strict-friendly check."""
    client = _build_mock_client(_example_room_brief())

    generate_room_brief(_example_brief_input(), client=client)

    kwargs = _captured_kwargs(client)
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "top_k" not in kwargs


def test_generate_room_brief_does_not_pass_budget_tokens_in_thinking():
    """budget_tokens was removed on Opus 4.7 — passing it would be a 400."""
    client = _build_mock_client(_example_room_brief())

    generate_room_brief(_example_brief_input(), client=client)

    kwargs = _captured_kwargs(client)
    assert "budget_tokens" not in kwargs["thinking"]


def test_generate_room_brief_caches_system_prompt_with_ephemeral_marker():
    """The last system block must carry cache_control ephemeral."""
    client = _build_mock_client(_example_room_brief())

    generate_room_brief(_example_brief_input(), client=client)

    kwargs = _captured_kwargs(client)
    system_blocks = cast(list[dict[str, Any]], kwargs["system"])
    assert isinstance(system_blocks, list)
    assert len(system_blocks) >= 1
    last_block = system_blocks[-1]
    assert last_block["type"] == "text"
    assert last_block["cache_control"] == {"type": "ephemeral"}
    # The text must be the full frozen system prompt.
    text = cast(str, last_block["text"])
    assert "RoomBrief" in text
    assert "target_lux_ambient" in text


def test_generate_room_brief_sends_one_user_message_with_room_context():
    client = _build_mock_client(_example_room_brief())

    generate_room_brief(_example_brief_input(), client=client)

    kwargs = _captured_kwargs(client)
    messages = cast(list[dict[str, Any]], kwargs["messages"])
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    user_content = cast(str, messages[0]["content"])
    # The serialised digest, standards, and brief should all be in the user msg.
    assert "Dining" in user_content
    assert "intent_mood" in user_content
    assert "entertain" in user_content
    assert "target_lux" in user_content


def test_generate_room_brief_uses_default_client_when_none_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `client=None`, generator should instantiate `anthropic.Anthropic()`."""
    fake_message = MagicMock()
    fake_message.parsed_output = _example_room_brief()
    fake_client = MagicMock()
    fake_client.messages.parse.return_value = fake_message

    def _factory(*_args: object, **_kwargs: object) -> MagicMock:
        return fake_client

    monkeypatch.setattr(
        "lighting_engine.brief.generator.anthropic.Anthropic",
        _factory,
    )

    result = generate_room_brief(_example_brief_input())
    assert result == _example_room_brief()
    fake_client.messages.parse.assert_called_once()
