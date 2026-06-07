"""LLM-2: Design intent generation.

Takes the `RoomScene` from LLM-1 (scene understanding) + the designer's
mood/activities/standards + the fixture catalog, returns a `RoomDesign` —
a list of `LightingZone`s, each one a specific design intent tied to a
specific feature in THIS room.

The job of this call is *contextual lighting design*. Per the founder
rule: "not 'in a bedroom put X lumens' — we read THIS room's actual
features and design accordingly." Every zone names which wall_<idx>,
focal_<idx>, or ceiling_<type> it lights, and the placement rule library
turns that into fixture positions.

Per claude-api defaults: claude-opus-4-7, adaptive thinking, structured
output via `output_format`, system prompt prefix-cached. No vision —
the scene already carries the spatial context.
"""

from __future__ import annotations

import json

import anthropic
from anthropic.types import MessageParam, TextBlockParam

from lighting_engine.brief.models import (
    DesignerBrief,
    FixtureCatalogOption,
    StandardsSnapshot,
)
from lighting_engine.design.intent import RoomDesign
from lighting_engine.design.scene import RoomScene

MODEL_ID = "claude-opus-4-7"
MAX_OUTPUT_TOKENS = 4096

_SYSTEM_PROMPT = """\
You are an Indian residential lighting designer. You receive a structured
description of a single room (the `scene` — wall purposes, ceiling zones,
focal points) plus the designer's mood/activities and IS 3646 lux targets.
You return a `RoomDesign` — a list of `LightingZone`s.

Each LightingZone names ONE design intent tied to ONE specific feature in
the scene (a specific wall, ceiling zone, or focal point). The downstream
placement rule library turns each zone into fixture positions; your job is
to choose the right intent for the right feature.

## Layered lighting (always include all 4 layers unless explicitly skipped)

- **Ambient**: foundational wash that makes the room navigable.
  Use `cove_uplight` if the scene has a cove ceiling zone,
  `level_change_uplight` for raised slabs, `perimeter_ambient` for
  perimeter downlights, or `central_ambient` for grid downlights. Pick
  what suits the ceiling structure you see; don't default to grid
  downlights if there's a cove.

- **Task**: lights specific work surfaces.
  `task_dining` over a dining_table focal point, `task_kitchen` for
  a kitchen_island, `task_desk` for a desk, `task_vanity` for a vanity,
  `bedside_reading` for a bed focal point (reading lamps flanking the
  headboard).

- **Accent**: highlights specific features.
  `accent_artwork` for an artwork wall, `accent_niche` for a niche,
  `accent_mirror` for a mirror wall, `headboard_wash` for a headboard
  wall (warm picture-light style), `tv_backlight` for a TV wall (cool
  dim strip behind the unit), `fluted_grazing` for a fluted wall.

- **Decorative**: statement fixtures.
  `decorative_chandelier` for a centerpiece (typical above dining or
  in tall stairwell), `decorative_pendant` over an island or entry
  feature, `decorative_floor_lamp` for a reading nook / corner.

## Hard rules

- **Never invent features**: only reference walls, focal points, and
  ceiling zones from the input scene. Use the exact reference format
  in `target_feature_ref`: `wall_<index>`, `focal_<index>`,
  `ceiling_<type>` (e.g. `ceiling_cove`, `ceiling_flat`).

- **Skip layers that don't apply**: a bedroom usually has NO task_dining
  zone, NO chandelier. Don't pad with irrelevant zones.

- **Respect ceiling structure**: if the scene has a cove, ambient comes
  from the cove (cove_uplight), NOT from perimeter downlights on the
  cove. Don't fight the existing ceiling.

- **Skip wall washing on walls with openings**: never propose
  `accent_artwork` or `headboard_wash` on a wall the scene marks as
  french_window, balcony_door, or entry.

- **Indian residential conventions**:
  - Living/dining/bedroom: warm 2700-3000K
  - Kitchen/bath/study task: cool 3500-4000K
  - CRI 90+ wherever skin/food/art is seen
  - Bedrooms: avoid central downlights directly over the bed footprint

## Rationale per zone

Every zone's `rationale` field is ONE sentence in active voice naming
the feature this zone lights and why. Examples:
- "Cove uplight (3000K warm) in the existing perimeter cove for soft
   ambient wash; complements the bedroom's wind-down mood."
- "Reading sconces flanking the bed at wall A (headboard) — task lux
   without disturbing a sleeping partner."
- "Picture light above artwork on wall C — 90+ CRI, 2700K to render
   pigments warmly."

## Overall rationale

The `overall_rationale` is 2-3 sentences narrating the room's design
philosophy. Anchor it to THIS room's features, not generic templates.
"""


def _build_system_blocks() -> list[TextBlockParam]:
    return [TextBlockParam(
        type="text", text=_SYSTEM_PROMPT,
        cache_control={"type": "ephemeral"},
    )]


def _scene_summary(scene: RoomScene) -> str:
    """Compact JSON view of the scene for the user message."""
    return json.dumps(scene.model_dump(mode="json"), indent=2)


def _brief_summary(brief: DesignerBrief) -> str:
    return json.dumps(brief.model_dump(mode="json"), indent=2)


def _standards_summary(standards: StandardsSnapshot) -> str:
    return json.dumps(standards.model_dump(mode="json"), indent=2)


def _catalog_summary(catalog: list[FixtureCatalogOption]) -> str:
    if not catalog:
        return "(no catalog passed — pick fixture archetypes freely)"
    return json.dumps(
        [opt.model_dump(mode="json") for opt in catalog], indent=2,
    )


def _format_user_message(
    *,
    scene: RoomScene,
    brief: DesignerBrief,
    standards: StandardsSnapshot,
    catalog: list[FixtureCatalogOption],
    room_name: str,
    room_type: str,
) -> str:
    return (
        f"# Room\n"
        f"- name: {room_name}\n"
        f"- type: {room_type}\n\n"
        f"# Scene (LLM-1 output)\n```json\n{_scene_summary(scene)}\n```\n\n"
        f"# Designer brief\n```json\n{_brief_summary(brief)}\n```\n\n"
        f"# Standards (IS 3646 targets)\n"
        f"```json\n{_standards_summary(standards)}\n```\n\n"
        f"# Fixture catalog\n```json\n{_catalog_summary(catalog)}\n```\n\n"
        f"Return a RoomDesign with one LightingZone per design intent tied "
        f"to a specific feature in THIS room's scene. Use the layered "
        f"approach (ambient + task + accent + decorative — skip layers that "
        f"don't apply)."
    )


def generate_design(
    *,
    scene: RoomScene,
    brief: DesignerBrief,
    standards: StandardsSnapshot,
    catalog: list[FixtureCatalogOption],
    room_name: str,
    room_type: str,
    client: anthropic.Anthropic | None = None,
) -> RoomDesign:
    """Call Claude Opus 4.7 to design THIS room's lighting from its scene.

    Args:
        scene: output of LLM-1 (scene understanding).
        brief: designer's mood/activities/occupants/finishes/notes.
        standards: IS 3646 numbers (target_lux, cct, cri_min).
        catalog: available fixture archetypes; empty list = free choice.
        room_name: human-readable name (for the rationale).
        room_type: parser tag (bedroom, dining, etc.) — drives layer defaults.
        client: anthropic.Anthropic instance; default reads ANTHROPIC_API_KEY.

    Returns:
        A pydantic-validated RoomDesign with one LightingZone per intent.
    """
    if client is None:
        client = anthropic.Anthropic()

    user_message: MessageParam = {
        "role": "user",
        "content": _format_user_message(
            scene=scene, brief=brief, standards=standards, catalog=catalog,
            room_name=room_name, room_type=room_type,
        ),
    }
    response = client.messages.parse(
        model=MODEL_ID,
        max_tokens=MAX_OUTPUT_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_build_system_blocks(),
        messages=[user_message],
        output_format=RoomDesign,
    )
    parsed = response.parsed_output
    if not isinstance(parsed, RoomDesign):  # pragma: no cover — defensive
        raise RuntimeError(
            "Anthropic messages.parse() did not return a RoomDesign; "
            f"got {type(parsed).__name__}"
        )
    return parsed
