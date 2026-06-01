"""Floor segmentation for multi-floor DWGs.

One residential DWG can contain multiple floor plans (e.g. ground + first)
laid out side by side in the same coordinate space. We detect floor anchors
from FLOOR text labels, then assign each wall/label to the nearest anchor
so wall-stitching can run per-floor.

Files with no FLOOR labels degrade gracefully to a single floor (callers
treat the absence of anchors as one implicit floor 0).
"""

import re
from dataclasses import dataclass

from ezdxf.entities.mtext import MText
from ezdxf.entities.text import Text
from ezdxf.layouts.layout import Modelspace

from lighting_engine.parser.mtext import strip_mtext_codes


@dataclass(frozen=True)
class FloorAnchor:
    name: str    # canonical floor name token (uppercased): "GROUND", "FIRST", "BASEMENT", ...
    x: float     # DXF units
    y: float


# Canonical floor name → integer level. Positive = upper floors, 0 = ground,
# negative = below grade.
FLOOR_LEVEL_MAP: dict[str, int] = {
    "BASEMENT": -1,
    "LOWER": -1,
    "GROUND": 0,
    "GF": 0,
    "MEZZANINE": 1,
    "FIRST": 1,
    "1ST": 1,
    "FF": 1,
    "UPPER": 1,
    "SECOND": 2,
    "2ND": 2,
    "SF": 2,
    "THIRD": 3,
    "3RD": 3,
    "TF": 3,
    "FOURTH": 4,
    "4TH": 4,
    "FIFTH": 5,
    "5TH": 5,
}


# Match e.g. "GROUND FLOOR", "1ST FLOOR", "FIRST FLOOR PLAN", "FF FLOOR"
_FLOOR_RE = re.compile(
    r"\b("
    r"GROUND|FIRST|SECOND|THIRD|FOURTH|FIFTH|"
    r"UPPER|LOWER|BASEMENT|MEZZANINE|"
    r"GF|FF|SF|TF|"
    r"1ST|2ND|3RD|4TH|5TH"
    r")\s*FLOOR\b",
    re.IGNORECASE,
)


def floor_level_for_name(name: str) -> int:
    """Map a floor name (e.g. 'GROUND', 'first', 'FF') to a canonical integer level."""
    return FLOOR_LEVEL_MAP.get(name.upper(), 0)


def detect_floor_anchors(msp: Modelspace) -> list[FloorAnchor]:
    """Walk MText/Text entities and return one FloorAnchor per FLOOR label found."""
    anchors: list[FloorAnchor] = []
    for e in msp.query("MTEXT TEXT"):
        if isinstance(e, MText):
            raw = e.text
        elif isinstance(e, Text):
            raw = e.dxf.text
        else:
            continue
        try:
            ip = e.dxf.insert
        except AttributeError:
            continue
        cleaned = strip_mtext_codes(raw)
        m = _FLOOR_RE.search(cleaned)
        if m:
            anchors.append(FloorAnchor(
                name=m.group(1).upper(),
                x=float(ip.x),
                y=float(ip.y),
            ))
    return anchors


def nearest_anchor_index(point: tuple[float, float], anchors: list[FloorAnchor]) -> int:
    """Return the index of the FloorAnchor closest to `point` (Euclidean)."""
    px, py = point
    best_i = 0
    best_d = float("inf")
    for i, a in enumerate(anchors):
        d = (a.x - px) ** 2 + (a.y - py) ** 2
        if d < best_d:
            best_d = d
            best_i = i
    return best_i
