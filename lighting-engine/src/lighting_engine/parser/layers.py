"""Heuristic layer-name → semantic role classification.

DWG layer names vary by firm but typically use predictable substrings. Order
matters: more specific roles (fixture's 'light') must match before generic
ones (wall's 'wall') so 'wall light' lands as a fixture, not a wall.
"""

from collections import defaultdict
from enum import StrEnum


class LayerRole(StrEnum):
    wall = "wall"
    window = "window"     # includes GLASS / balcony-door glazing
    door = "door"
    fixture = "fixture"
    furniture = "furniture"
    annotation = "annotation"
    ceiling_feature = "ceiling_feature"
    north_arrow = "north_arrow"


# Ordered: each role checks substrings against the layer name (lowercased).
# Earlier roles win, so put specific (e.g. fixture's 'light') before generic ('wall').
_ROLE_HINTS: list[tuple[LayerRole, tuple[str, ...]]] = [
    (LayerRole.fixture,        ("light", "rcp", "downlight", "chandelier",
                                "cove", "fixture", "luminaire", "lamp",
                                "electrical")),
    (LayerRole.window,         ("window", "glass", "glaz")),
    (LayerRole.door,           ("door",)),
    (LayerRole.furniture,      ("furn", "sofa", "bed", "cupboard")),
    (LayerRole.ceiling_feature, ("ceiling", "beam", "soffit", "cove",
                                 "drop", "height_change")),
    (LayerRole.north_arrow,    ("north",)),
    (LayerRole.wall,           ("wall", "column", "stone")),
    (LayerRole.annotation,     ("dim", "text", "annot", "label")),
]


def classify_layers(layer_names: list[str]) -> dict[LayerRole, list[str]]:
    """Group layer names by role. A layer is assigned to the FIRST matching role."""
    result: dict[LayerRole, list[str]] = defaultdict(list)
    for name in layer_names:
        lower = name.lower()
        for role, hints in _ROLE_HINTS:
            if any(h in lower for h in hints):
                result[role].append(name)
                break
    # Ensure every role is present (possibly empty) for stable downstream code
    for role in LayerRole:
        result.setdefault(role, [])
    return dict(result)
