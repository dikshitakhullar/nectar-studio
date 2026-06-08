"""Feature flag for the v1 lighting-designer pipeline.

ON  → scene → design → place (contextual)
OFF → legacy brief + multi-layer placement (current production behavior)

The flag must be explicitly ON AND an Anthropic API key must be present.
If either is missing, the legacy pipeline runs (no regression risk).
"""
import os


def is_v1_designer_enabled() -> bool:
    """True only when the feature flag is on AND an API key is configured."""
    flag = os.environ.get("LIGHTING_ENGINE_USE_V1_DESIGNER", "false")
    if flag.lower() not in ("true", "1", "yes"):
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
