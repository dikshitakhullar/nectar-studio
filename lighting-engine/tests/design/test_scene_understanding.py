"""Tests for scene_understanding — mocked Anthropic client.

End-to-end with real Claude lives in tests/integration/ (gated on
ANTHROPIC_API_KEY).
"""

from unittest.mock import MagicMock

import pytest

from lighting_engine.design.scene import (
    CeilingZone,
    FocalPoint,
    RoomScene,
    WallPurpose,
)
from lighting_engine.design.scene_understanding import (
    _build_user_message,
    _format_user_text,
    understand_scene,
)
from lighting_engine.models.geometry import (
    Door,
    DoorSwing,
    Furniture,
    Point,
    Project,
    Room,
    Window,
)


def _bedroom() -> tuple[Project, Room]:
    room = Room(
        id="r1", name="MASTER BEDROOM", type="bedroom", floor_level=0,
        polygon=[
            Point(x=0, y=0), Point(x=5, y=0),
            Point(x=5, y=4), Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
        doors=[Door(
            id="d1", position=Point(x=2.5, y=0),
            wall_index=0, along_wall=0.5,
            width_m=0.9, swing=DoorSwing.in_,
        )],
        windows=[Window(
            id="w1", position=Point(x=5, y=2),
            wall_index=1, along_wall=0.5,
            width_m=1.2, height_m=1.2, sill_height_m=0.9,
        )],
        furniture=[Furniture(
            id="f1", type="BED", raw_label="BED-DOUBLE",
            position=Point(x=2.5, y=2),
        )],
    )
    return Project(id="p", name="x", rooms=[room]), room


def test_format_user_text_includes_room_metadata():
    _, room = _bedroom()
    text = _format_user_text(room=room, ceiling_type="cove")
    assert "MASTER BEDROOM" in text
    assert "Walls: 4" in text
    assert "cove" in text
    assert "Ceiling height: 2.70m" in text
    assert "door on wall A" in text
    assert "window on wall B" in text
    assert "BED-DOUBLE" in text


def test_format_user_text_handles_unset_ceiling_type():
    _, room = _bedroom()
    text = _format_user_text(room=room, ceiling_type=None)
    assert "unset" in text


def test_build_user_message_includes_image_and_text():
    _, room = _bedroom()
    png = b"\x89PNG\r\n\x1a\nfake-png-bytes"
    msg = _build_user_message(room=room, image_png=png, ceiling_type="flat")
    assert msg["role"] == "user"
    content = msg["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "image"
    assert content[0]["source"]["type"] == "base64"
    assert content[1]["type"] == "text"


def test_understand_scene_calls_claude_and_parses_response():
    project, _ = _bedroom()

    expected_scene = RoomScene(
        walls=[
            WallPurpose(wall_index=0, purpose="entry", confidence=0.9),
            WallPurpose(wall_index=1, purpose="french_window", confidence=0.85),
            WallPurpose(wall_index=2, purpose="headboard", confidence=0.95),
            WallPurpose(wall_index=3, purpose="wardrobe", confidence=0.8),
        ],
        ceiling=[CeilingZone(type="flat", description="flat POP ceiling", confidence=0.9)],
        focal_points=[FocalPoint(
            type="bed", position=Point(x=2.5, y=2),
            purpose_hint="king bed centered against wall C",
        )],
        notes="Master bedroom with bed against wall C, French window on east.",
        confidence=0.88,
    )

    fake_response = MagicMock()
    fake_response.parsed_output = expected_scene
    fake_client = MagicMock()
    fake_client.messages.parse.return_value = fake_response

    result = understand_scene(project=project, room_id="r1", client=fake_client)

    assert result == expected_scene
    # Verify the API call was made with the right model + thinking config
    call_kwargs = fake_client.messages.parse.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-7"
    assert call_kwargs["thinking"] == {"type": "adaptive"}
    assert call_kwargs["output_format"] is RoomScene
    # The system block carries cache_control for prompt caching
    sys_blocks = call_kwargs["system"]
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_understand_scene_rejects_unknown_room_id():
    project, _ = _bedroom()
    with pytest.raises(ValueError, match="not in project"):
        understand_scene(project=project, room_id="bogus", client=MagicMock())
