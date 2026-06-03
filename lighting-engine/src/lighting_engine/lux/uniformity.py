"""Compute lux uniformity stats from a placed layout.

Model: each fixture is a point source with a finite beam angle. For each grid
point at work-plane height, compute the cosine-corrected inverse-square
contribution if the point lies inside the fixture's beam cone, else zero. Sum
contributions across all fixtures.

`E = I * cos(theta) / d^2`
  - E      illuminance at the point, in lux
  - I      candela intensity, approximated as
              lumens / (2 * pi * (1 - cos(half_beam_rad)))
  - theta  angle from vertical (fixture pointing down) to the grid point
  - d      slant distance from fixture to grid point
"""

import math

from lighting_engine.models.geometry import Fixture, Point

_DEFAULT_MOUNT_HEIGHT_M = 2.7
_WORK_PLANE_HEIGHT_M = 0.8
_DEFAULT_BEAM_ANGLE_DEG = 60.0


def _candela_from_lumens(lumens: float, beam_angle_deg: float) -> float:
    """Convert total lumens to nominal candela for a downlight with the given beam."""
    half_rad = math.radians(beam_angle_deg / 2.0)
    solid_angle = 2.0 * math.pi * (1.0 - math.cos(half_rad))
    if solid_angle <= 0:
        return 0.0
    return lumens / solid_angle


def point_source_lux_at(
    fixture: Fixture,
    point: Point,
    *,
    work_plane_height_m: float = _WORK_PLANE_HEIGHT_M,
) -> float:
    """Lux contribution from one fixture at one (x, y) grid point on the work plane.

    Returns 0.0 when:
      - the fixture sits at or below the work plane (vertical drop <= 0)
      - the grid point falls outside the fixture's beam cone
      - the fixture has no lumens specified
    """
    mount = fixture.mount_height_m if fixture.mount_height_m else _DEFAULT_MOUNT_HEIGHT_M
    vertical = mount - work_plane_height_m
    if vertical <= 0:
        return 0.0
    horizontal = math.hypot(
        point.x - fixture.position.x,
        point.y - fixture.position.y,
    )
    distance = math.hypot(horizontal, vertical)
    if distance <= 0:
        return 0.0
    cos_theta = vertical / distance

    beam = fixture.beam_angle_deg or _DEFAULT_BEAM_ANGLE_DEG
    half_beam = math.radians(beam / 2.0)
    theta = math.acos(cos_theta)
    if theta > half_beam:
        return 0.0

    lumens = fixture.lumens or 0.0
    candela = _candela_from_lumens(lumens, beam)
    return candela * cos_theta / (distance * distance)
