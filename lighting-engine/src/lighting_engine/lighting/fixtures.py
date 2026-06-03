"""Fixture catalog for v0 — two generic LED downlights.

The design doc puts product catalog data (real Wipro/Havells/Philips SKUs) in
a structured DB to come later. For v0 placement we just need two stand-in
fixtures so the lumen-method has something to count.
"""

from dataclasses import dataclass

from lighting_engine.lighting.standards import LuxStandard
from lighting_engine.models.geometry import RoomType


@dataclass(frozen=True)
class FixtureSpec:
    """A choosable downlight (or other ambient fixture) for the placement engine."""
    sku: str                  # internal identifier; later maps to a real catalog entry
    name: str
    wattage_w: float
    lumens: float
    cct_k: int                # 2700, 3000, 4000, ...
    cri: int                  # 80, 90, 95
    beam_angle_deg: float
    s_mh_ratio: float = 1.5   # spacing-to-mounting-height (typical residential ambient)


# Indian residential default skews warm. Both fixtures are 12W / 1200lm / CRI 90 —
# same architectural form, just different CCT.
DEFAULT_WARM_DOWNLIGHT = FixtureSpec(
    sku="GEN-DL-12-2700",
    name="12W warm downlight",
    wattage_w=12.0,
    lumens=1200.0,
    cct_k=2700,
    cri=90,
    beam_angle_deg=60.0,
)

DEFAULT_COOL_DOWNLIGHT = FixtureSpec(
    sku="GEN-DL-12-4000",
    name="12W cool downlight",
    wattage_w=12.0,
    lumens=1200.0,
    cct_k=4000,
    cri=90,
    beam_angle_deg=60.0,
)


def pick_default_fixture(
    room_type: RoomType, standard: LuxStandard,
) -> FixtureSpec:
    """Choose warm vs cool downlight based on the room type's preferred CCT.

    Warm (2700K) for living areas, bedrooms, dining, foyer — anywhere relaxation
    or hospitality matters. Cool (4000K) for task rooms where colour discrimination
    helps: kitchen, bath, study. Threshold: CCT >= 3200K → cool.
    """
    if standard.cct_k >= 3200:
        return DEFAULT_COOL_DOWNLIGHT
    return DEFAULT_WARM_DOWNLIGHT
