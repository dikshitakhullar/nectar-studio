"""LLM-1: Scene understanding.

Reads a rendered room PNG + structured room metadata, returns a `RoomScene`
identifying wall purposes, ceiling zones, and focal points.

The job of this call is *contextual perception*, not lighting design.
Claude says "wall A is the headboard wall, wall C has the French window
to the balcony, ceiling has a cove around a flat central panel." LLM-2
(intent generation) uses that scene to design the lighting.

Per claude-api defaults: claude-opus-4-7, adaptive thinking, structured
output via `output_format`, system prompt prefix-cached, vision content
block carries the rendered PNG.
"""

from __future__ import annotations

import base64

import anthropic
from anthropic.types import (
    Base64ImageSourceParam,
    ImageBlockParam,
    MessageParam,
    TextBlockParam,
)

from lighting_engine.design.room_render import render_room_for_vision
from lighting_engine.design.scene import RoomScene
from lighting_engine.models.geometry import Project, Room

MODEL_ID = "claude-opus-4-7"
MAX_OUTPUT_TOKENS = 4096

_SYSTEM_PROMPT = """\
You read residential floor-plan crops and identify the design context for a
single highlighted room. Your output is consumed by a lighting design agent
that will design THIS specific room's lighting from your scene description.

## What you see in the image

- The target room is highlighted in yellow with a bold black outline.
- Same-floor neighbor rooms are shown in grayscale with their labels.
- Each wall of the target room is labeled A, B, C, ... going around the
  polygon (the letter sits OUTSIDE the room next to the wall).
- Doors are drawn as standard architectural quarter-arc swing symbols
  (the arc opens into the room).
- Windows are drawn as thick blue double-lines on the wall.
- A small north arrow sits near the top-left of the target.
- Furniture footprints are shown as tan polygons with their labels.

## What you produce

A `RoomScene` describing:

1. **Per-wall purpose** — for EACH wall (A, B, C, ...), choose the purpose
   that best fits this room type and the wall's surroundings:
   - "headboard"     — the wall the head of the bed is against (bedroom)
   - "tv"            — the wall a TV unit faces or is mounted on
   - "artwork"       — feature wall with art (often opposite TV)
   - "blank"         — no notable feature — but try to use a specific
                       purpose first; "blank" is the fallback
   - "fluted"        — fluted-panel surface treatment
   - "french_window" — wall has a floor-to-ceiling window/door to balcony
   - "balcony_door"  — wall has a sliding/swing door to a balcony
   - "entry"         — wall the room is entered through
   - "wardrobe"      — built-in wardrobe wall
   - "feature_panel" — paneled / textured feature wall (not fluted)
   - "mirror"        — mirror wall
   - "bookshelf"     — built-in bookshelf wall
   Each wall gets a confidence 0-1 reflecting how sure you are.

2. **Ceiling zones** — list the ceiling structure. For the MVP we work
   with a single ceiling-type tag (passed in the user message), so a
   bedroom with a cove ceiling becomes a list like:
     [{type:"cove", description:"perimeter cove around central flat panel"},
      {type:"flat", description:"central flat panel"}]
   If the room basics say `ceiling_type=flat`, return a single flat zone.

3. **Focal points** — name SPECIFIC pieces of furniture that anchor the
   lighting design:
   - "bed" for any bedroom (position = bed centroid; purpose_hint should
     describe orientation, e.g. "head end against wall A")
   - "dining_table", "sofa", "desk", "vanity", "kitchen_island", "puja_altar"
   Position is in room-local meters (same frame as the polygon).
   Estimate the position from what you can see; don't invent furniture
   that isn't there.

4. **Notes** — 1-2 sentences capturing the design narrative for this room
   ("Master bedroom with a cove ceiling and the bed centered against the
   north wall, French window to the balcony on the east wall").

5. **Confidence** — your overall confidence in the scene reading.

## Key rules

- Wall letters in your output MUST match the letters drawn on the image.
- `wall_index` corresponds to the polygon edge from vertex i → i+1; wall A
  is index 0, B is 1, etc.
- Indian residential conventions: windows are often French windows opening
  onto balconies; bedrooms typically have one headboard wall and an
  opposing wall (often with a TV or wardrobe).
- Never guess focal points you can't justify from the visible furniture
  footprints or the room type.
"""


def _build_system_blocks() -> list[TextBlockParam]:
    """System prompt with ephemeral cache_control on the last block.

    Renders order is tools → system → messages; placing cache_control on
    the system block caches the system prefix across calls in a session.
    """
    return [TextBlockParam(
        type="text", text=_SYSTEM_PROMPT,
        cache_control={"type": "ephemeral"},
    )]


def _format_user_text(*, room: Room, ceiling_type: str | None) -> str:
    """Build the text part of the vision user message."""
    n_walls = len(room.polygon)
    wall_letters = [chr(65 + i) for i in range(n_walls)]
    parts = [
        f"Room name: {room.name}",
        f"Room type (parser tag): {room.type}",
        f"Walls: {n_walls} ({', '.join(wall_letters)})",
        f"Ceiling type (designer): {ceiling_type or 'unset'}",
    ]
    if room.ceiling_height_m:
        parts.append(f"Ceiling height: {room.ceiling_height_m:.2f}m")
    if room.doors:
        door_descs = [
            f"door on wall {chr(65 + d.wall_index)}"
            for d in room.doors if d.wall_index is not None
        ]
        if door_descs:
            parts.append("Detected doors: " + "; ".join(door_descs))
    if room.windows:
        win_descs = [
            f"window on wall {chr(65 + w.wall_index)}"
            for w in room.windows if w.wall_index is not None
        ]
        if win_descs:
            parts.append("Detected windows: " + "; ".join(win_descs))
    if room.furniture:
        labels = [f.raw_label or f.type or "furniture" for f in room.furniture]
        parts.append("Detected furniture: " + ", ".join(labels[:8]))
    return "\n".join(parts) + (
        "\n\nIdentify the design context for THIS room and return a RoomScene."
    )


def _build_user_message(
    *, room: Room, image_png: bytes, ceiling_type: str | None,
) -> MessageParam:
    image_b64 = base64.b64encode(image_png).decode("ascii")
    return {
        "role": "user",
        "content": [
            ImageBlockParam(
                type="image",
                source=Base64ImageSourceParam(
                    type="base64",
                    media_type="image/png",
                    data=image_b64,
                ),
            ),
            TextBlockParam(
                type="text",
                text=_format_user_text(room=room, ceiling_type=ceiling_type),
            ),
        ],
    }


def understand_scene(
    *,
    project: Project,
    room_id: str,
    ceiling_type: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> RoomScene:
    """Call Claude Opus 4.7 to read THIS room's design context.

    Args:
        project: the full project IR (renderer needs neighbor polygons).
        room_id: the target room.
        ceiling_type: designer's ceiling-type tag (`cove`, `flat`, etc.)
            passed verbatim into the prompt. None falls back to "unset".
        client: anthropic.Anthropic instance; default reads ANTHROPIC_API_KEY.

    Returns:
        A pydantic-validated RoomScene describing wall purposes, ceiling
        zones, focal points, and a design narrative.

    Raises:
        anthropic.APIError on transport / API failures.
        ValueError if `room_id` is not in the project.
    """
    room = next((r for r in project.rooms if r.id == room_id), None)
    if room is None:
        raise ValueError(f"room {room_id!r} not in project {project.id!r}")

    if client is None:
        client = anthropic.Anthropic()

    image_png = render_room_for_vision(project=project, room_id=room_id)
    system_blocks = _build_system_blocks()
    user_message = _build_user_message(
        room=room, image_png=image_png, ceiling_type=ceiling_type,
    )

    response = client.messages.parse(
        model=MODEL_ID,
        max_tokens=MAX_OUTPUT_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=system_blocks,
        messages=[user_message],
        output_format=RoomScene,
    )
    parsed = response.parsed_output
    if not isinstance(parsed, RoomScene):  # pragma: no cover — defensive
        raise RuntimeError(
            "Anthropic messages.parse() did not return a RoomScene; "
            f"got {type(parsed).__name__}"
        )
    return parsed
