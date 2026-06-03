"""Lux / CCT / CRI standards by room type — typed table, **never** RAG-retrieved.

Per the design doc §3: numbers the math depends on must be deterministic. This
file is the single source of truth for what room types want for ambient lux,
preferred colour temperature, and minimum CRI.

Sources:
- IS 3646 Part 1 (India interior illuminance)
- IES Lighting Handbook (residential targets)
- `docs/research/lighting/03-room-by-room.md` (encoded as code)
"""

from dataclasses import dataclass

from lighting_engine.models.geometry import RoomType


@dataclass(frozen=True)
class LuxStandard:
    """Per-room-type ambient targets the lumen-method consumes."""
    target_lux: float       # ambient illuminance target on the work plane
    cct_k: int              # preferred colour temperature in Kelvin
    cri_min: int            # minimum colour rendering index
    place_ambient: bool = True   # False for room types we don't place ambient in v0


# Ambient-only targets. Task / accent / decorative are v1.
# Indian residential default skews WARM (2700–3000K) per docs/research/lighting/.
_TABLE: dict[RoomType, LuxStandard] = {
    RoomType.living:    LuxStandard(target_lux=150, cct_k=2700, cri_min=90),
    RoomType.dining:    LuxStandard(target_lux=200, cct_k=2700, cri_min=90),
    RoomType.bedroom:   LuxStandard(target_lux=100, cct_k=2700, cri_min=90),
    # Task rooms — cooler CCT for colour accuracy (food prep, grooming, focus)
    RoomType.kitchen:   LuxStandard(target_lux=300, cct_k=4000, cri_min=90),
    RoomType.bathroom:  LuxStandard(target_lux=200, cct_k=4000, cri_min=90),
    RoomType.study:     LuxStandard(target_lux=300, cct_k=4000, cri_min=90),
    RoomType.foyer:     LuxStandard(target_lux=200, cct_k=3000, cri_min=90),
    RoomType.hallway:   LuxStandard(target_lux=75,  cct_k=3000, cri_min=80),
    # v0 skips these — they need different lighting (path lights, step lights,
    # landscape lighting) handled in a later layer.
    RoomType.outdoor:   LuxStandard(target_lux=0, cct_k=3000, cri_min=80, place_ambient=False),
    RoomType.staircase: LuxStandard(target_lux=0, cct_k=3000, cri_min=80, place_ambient=False),
    # Safe default — fall through for unrecognised room names
    RoomType.unknown:   LuxStandard(target_lux=200, cct_k=3000, cri_min=90),
}


def get_lux_standard(room_type: RoomType) -> LuxStandard:
    """Return the typed standard for a room type. Always defined for every enum."""
    return _TABLE[room_type]
