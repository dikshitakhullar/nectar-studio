"""The lumen method — core photometric math for ambient placement.

Formula:
    required_lumens = (target_lux × area_sqm) / (UF × MF)
    fixture_count   = ceil(required_lumens / fixture_lumens)

UF (utilization factor) is the fraction of fixture lumens that reach the work
plane; depends on room reflectances and geometry. For typical Indian residential
spaces (ceiling 0.7 / walls 0.5 / floor 0.25) we use a constant 0.5 for v0. A
proper UF table comes from the IES Lighting Handbook — defer to v1.

MF (maintenance factor) accounts for fixture dirt, lamp depreciation, surface
aging. 0.8 is the textbook residential default.
"""

import math

# Constants — typed in code, NEVER fuzzy-retrieved.
UTILIZATION_FACTOR = 0.5     # fraction of fixture lumens reaching the work plane
MAINTENANCE_FACTOR = 0.8     # dirt + lamp depreciation derating
WORK_PLANE_HEIGHT_M = 0.8    # typical desk/counter height


def required_lumens(
    target_lux: float,
    area_sqm: float,
    *,
    uf: float = UTILIZATION_FACTOR,
    mf: float = MAINTENANCE_FACTOR,
) -> float:
    """Total downlight lumens needed to achieve `target_lux` on the work plane."""
    if target_lux <= 0 or area_sqm <= 0:
        return 0.0
    return (target_lux * area_sqm) / (uf * mf)


def fixture_count_for_room(
    target_lux: float,
    area_sqm: float,
    fixture_lumens: float,
    *,
    uf: float = UTILIZATION_FACTOR,
    mf: float = MAINTENANCE_FACTOR,
) -> int:
    """How many fixtures of the given lumens are needed to hit the target."""
    if target_lux <= 0 or area_sqm <= 0 or fixture_lumens <= 0:
        return 0
    needed = required_lumens(target_lux, area_sqm, uf=uf, mf=mf)
    return max(1, math.ceil(needed / fixture_lumens))


def spacing_m(s_mh_ratio: float, ceiling_height_m: float) -> float:
    """Maximum fixture-to-fixture spacing per the S/MH ratio.

    `mounting height` is the ceiling-to-work-plane distance. Beyond this spacing,
    the cones of light from adjacent fixtures stop overlapping at the work plane
    and a dark scallop appears between them.
    """
    mh = max(ceiling_height_m - WORK_PLANE_HEIGHT_M, 0.5)
    return s_mh_ratio * mh
