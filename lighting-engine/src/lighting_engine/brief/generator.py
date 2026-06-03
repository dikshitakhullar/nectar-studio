"""Single-call LLM brief generator.

Calls Claude Opus 4.7 with:
  * a FROZEN cached system prompt (~6K tokens of lighting science + IS 3646
    + room-by-room + Indian residential context + RoomBrief JSON schema).
  * a per-room user message containing the RoomDigest, designer brief,
    standards numbers, and fixture catalog options.
  * `thinking: {type: "adaptive"}` and `output_config: {effort: "high"}` —
    Opus 4.7 conventions (no `budget_tokens`, no temperature/top_p/top_k).
  * structured outputs via `messages.parse(output_format=RoomBrief)`.

The system prompt block carries `cache_control: {"type": "ephemeral"}` so
the prefix caches across all calls within the 5-minute TTL. Verify with
`response.usage.cache_read_input_tokens` in tests.
"""

import json
from typing import TYPE_CHECKING

import anthropic
from anthropic.types import MessageParam, TextBlockParam

from lighting_engine.brief.models import BriefInput, RoomBrief
from lighting_engine.brief.prompts import build_system_prompt

if TYPE_CHECKING:
    # Only used for the static type hint on `_serialise_user_message`.
    pass


# Frozen Opus 4.7 model identifier. Pinned — switching the model invalidates
# the prompt cache (caches are model-scoped per shared/prompt-caching.md).
MODEL_ID = "claude-opus-4-7"

# Max tokens for the response. A typical RoomBrief is ~1.5-3K tokens
# including the design_rationale text + ~5 zones. 4096 leaves headroom for
# the elderly + accent-heavy cases.
MAX_OUTPUT_TOKENS = 4096


def _serialise_user_message(brief_input: BriefInput) -> str:
    """Render the per-room user message as deterministic-but-not-cached prose.

    This message is what *varies* per request. It does NOT need to be
    byte-stable across calls — we don't put a cache_control marker on it.
    But we still serialise the JSON deterministically so two identical
    inputs produce identical bytes (useful for regression tests).
    """
    digest_blob = brief_input.digest.model_dump(mode="json")
    confirmed_blob = brief_input.confirmed_room.model_dump(mode="json")
    standards_blob = brief_input.standards.model_dump(mode="json")
    catalog_blob = [fc.model_dump(mode="json") for fc in brief_input.fixture_catalog]

    parts: list[str] = []

    parts.append("# Room context")
    parts.append("")
    parts.append("## Spatial digest (resolved facts — no coordinate math required)")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(digest_blob, sort_keys=True, indent=2))
    parts.append("```")
    parts.append("")
    parts.append("## Designer clarifications + brief")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(confirmed_blob, sort_keys=True, indent=2))
    parts.append("```")
    parts.append("")
    parts.append("## Standards floor for this room type (IS 3646 / IES)")
    parts.append("")
    parts.append("Use as a starting point. You may push lux higher for elderly or task-heavy use.")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(standards_blob, sort_keys=True, indent=2))
    parts.append("```")
    parts.append("")
    parts.append("## Available fixture archetypes (reference — pick types, not SKUs)")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(catalog_blob, sort_keys=True, indent=2))
    parts.append("```")
    parts.append("")
    parts.append("## Your task")
    parts.append("")
    parts.append(
        "Emit a single RoomBrief JSON object that fits this room's geometry, the "
        "designer's intent, the occupant mix, and the time-of-use. Name the "
        "layer gap in `design_rationale`. Use the schema and rules from your "
        "system instructions."
    )

    return "\n".join(parts)


def _build_system_blocks() -> list[TextBlockParam]:
    """Render the cached system prompt as a single TextBlockParam list.

    The cache_control marker goes on the LAST block; per
    `shared/prompt-caching.md`, the render order is tools → system → messages,
    so a marker on the last system block caches both tools (none here) and
    system together.
    """
    system_text = build_system_prompt()
    return [
        TextBlockParam(
            type="text",
            text=system_text,
            cache_control={"type": "ephemeral"},
        ),
    ]


def generate_room_brief(
    brief_input: BriefInput,
    *,
    client: anthropic.Anthropic | None = None,
) -> RoomBrief:
    """Call Claude Opus 4.7 and return a validated RoomBrief.

    Args:
        brief_input: digest + clarifications + standards + fixture catalog.
        client: Anthropic client. If None, uses the default (reads
            ANTHROPIC_API_KEY from env).

    Returns:
        A pydantic-validated RoomBrief instance.

    Raises:
        anthropic.APIError on any API-side failure (rate limit, auth, etc).
        pydantic.ValidationError if the model returns malformed JSON
            (should not happen with output_config.format strict mode).
    """
    if client is None:
        client = anthropic.Anthropic()

    system_blocks = _build_system_blocks()
    user_message: MessageParam = {
        "role": "user",
        "content": _serialise_user_message(brief_input),
    }

    response = client.messages.parse(
        model=MODEL_ID,
        max_tokens=MAX_OUTPUT_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=system_blocks,
        messages=[user_message],
        output_format=RoomBrief,
    )

    # `messages.parse` populates `response.parsed_output` with a validated
    # RoomBrief instance when output_format is a pydantic model.
    parsed = response.parsed_output
    if not isinstance(parsed, RoomBrief):  # pragma: no cover — defensive
        raise RuntimeError(
            "Anthropic messages.parse() did not return a RoomBrief; "
            f"got {type(parsed).__name__}"
        )
    return parsed
