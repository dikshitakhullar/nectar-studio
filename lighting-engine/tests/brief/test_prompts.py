"""Tests guarding the FROZEN cached system prompt.

The whole point of the cache is that the prefix is byte-stable. These tests
catch silent invalidators (datetime.now, UUIDs, unsorted JSON) before they
ship to production and torch our cache-hit rate.
"""

import re

from lighting_engine.brief.prompts import build_system_prompt

# A char/token ratio of ~4 is the conservative english-prose approximation.
# Anthropic's tokenizer for Opus 4.7 hits closer to ~3.6 chars/token on
# technical prose, but ~4 is safe for an upper-bound check.
APPROX_CHARS_PER_TOKEN = 4


def test_system_prompt_is_deterministic_across_calls():
    """Repeated calls must produce byte-identical bytes — that's the contract."""
    first = build_system_prompt()
    for _ in range(5):
        again = build_system_prompt()
        assert again == first, "system prompt is not deterministic across calls"


def test_system_prompt_has_no_datetime_artifacts():
    """No `datetime.now()` / ISO-8601 timestamps anywhere in the prefix."""
    prompt = build_system_prompt()
    # Match common timestamp shapes: 2024-..., 2025-..., 2026-...
    assert re.search(r"\b20\d{2}-\d{2}-\d{2}", prompt) is None, (
        "system prompt contains a date — silent cache invalidator"
    )
    # Match HH:MM:SS
    assert re.search(r"\b\d{2}:\d{2}:\d{2}\b", prompt) is None
    # No literal "datetime" or "isoformat" usage leaking through
    assert "datetime.now" not in prompt
    assert "isoformat" not in prompt


def test_system_prompt_has_no_uuids():
    prompt = build_system_prompt()
    # Standard UUID4 pattern (with or without hyphens).
    uuid_pattern = re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    )
    assert uuid_pattern.search(prompt) is None, (
        "system prompt contains a UUID — silent cache invalidator"
    )


def test_system_prompt_fits_under_10k_tokens():
    """Hard ceiling — the brainstormed budget was 5–8K, 10K is the wall.

    Uses a chars-per-token approximation. Replace with a real tokenizer if
    we ever need a tighter bound.
    """
    prompt = build_system_prompt()
    approx_tokens = len(prompt) // APPROX_CHARS_PER_TOKEN
    assert approx_tokens < 10000, (
        f"system prompt approx tokens={approx_tokens} exceeds 10K ceiling"
    )


def test_system_prompt_is_substantial_enough_to_cache():
    """Opus 4.7 needs ≥4096 tokens of prefix to cache at all.

    See `shared/prompt-caching.md` — shorter prefixes silently won't cache.
    """
    prompt = build_system_prompt()
    approx_tokens = len(prompt) // APPROX_CHARS_PER_TOKEN
    assert approx_tokens >= 3500, (
        f"system prompt approx tokens={approx_tokens} too small "
        f"to clear Opus 4.7's 4096-token cacheable-prefix floor"
    )


def test_system_prompt_embeds_room_brief_schema():
    """The RoomBrief schema must be in the prompt so the LLM sees field names."""
    prompt = build_system_prompt()
    for field in (
        "target_lux_ambient",
        "cct_main",
        "fixture_preference",
        "layers_needed",
        "zones",
        "design_rationale",
        "warnings",
    ):
        assert field in prompt, f"RoomBrief field `{field}` missing from prompt"


def test_system_prompt_covers_indian_residential_context():
    """Sanity — content sourced from docs/research/lighting/."""
    prompt = build_system_prompt()
    lowered = prompt.lower()
    for keyword in (
        "is 3646",
        "puja",
        "warm-bias",
        "ambient",
        "task",
        "accent",
        "decorative",
        "elderly",
        "2700",
        "cri",
    ):
        assert keyword in lowered, f"prompt missing keyword: {keyword!r}"


def test_system_prompt_uses_sorted_json_for_schema():
    """The schema fence inside the prompt must be sorted-key JSON.

    Parse the embedded schema and verify each object's keys come back in
    alphabetical order — the canonical signal that `json.dumps(..., sort_keys=True)`
    was used.
    """
    import json as _json

    prompt = build_system_prompt()
    fence_start = prompt.find("```json")
    assert fence_start != -1, "schema fence not found"
    body_start = prompt.find("\n", fence_start) + 1
    fence_end = prompt.find("```", body_start)
    assert fence_end != -1, "schema fence end not found"
    schema_text = prompt[body_start:fence_end].strip()
    # `json.loads` with `object_pairs_hook` lets us see the original key order.
    bad: list[str] = []

    def _check(pairs: list[tuple[str, object]]) -> dict[str, object]:
        keys = [k for k, _ in pairs]
        if keys != sorted(keys):
            bad.append(",".join(keys))
        return dict(pairs)

    _json.loads(schema_text, object_pairs_hook=_check)
    assert not bad, f"schema JSON inside prompt is not sorted: {bad[:3]}"
