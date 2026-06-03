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

from pydantic import BaseModel
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.models.geometry import Fixture, Point, Room

_DEFAULT_MOUNT_HEIGHT_M = 2.7
_WORK_PLANE_HEIGHT_M = 0.8
_DEFAULT_BEAM_ANGLE_DEG = 60.0
_GRID_STEP_M = 0.5
_MEETS_TARGET_RATIO = 0.9


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


class LuxStats(BaseModel):
    """Aggregate illuminance stats for one room's work plane.

    `uniformity = min_lux / mean_lux`; `meets_target` is true when the mean
    illuminance reaches at least 90 percent of the brief's target lux.
    """

    mean_lux: float
    min_lux: float
    max_lux: float
    uniformity: float
    target_lux: float
    meets_target: bool
    sample_count: int


def _sample_grid_points(
    polygon: list[Point], step_m: float = _GRID_STEP_M,
) -> list[Point]:
    """Lay a regular grid over the polygon bbox; keep only points inside the polygon.

    The first sample is offset by half a step so corners and edges aren't
    biased — each sample represents the centre of a `step_m`-side cell.
    """
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    shape = ShapelyPolygon([(p.x, p.y) for p in polygon])
    points: list[Point] = []
    x = minx + step_m / 2.0
    while x < maxx:
        y = miny + step_m / 2.0
        while y < maxy:
            if shape.contains(ShapelyPoint(x, y)):
                points.append(Point(x=x, y=y))
            y += step_m
        x += step_m
    return points


def compute_uniformity(
    room: Room,
    fixtures: list[Fixture],
    *,
    target_lux: float,
    work_plane_height_m: float = _WORK_PLANE_HEIGHT_M,
    grid_step_m: float = _GRID_STEP_M,
) -> LuxStats:
    """Compute mean/min/max/uniformity for `fixtures` sampled over `room`.

    Returns an all-zero `LuxStats` (with `meets_target=False`) when either the
    polygon yields no interior grid points or `fixtures` is empty.
    """
    grid = _sample_grid_points(room.polygon, step_m=grid_step_m)
    if not grid or not fixtures:
        return LuxStats(
            mean_lux=0.0,
            min_lux=0.0,
            max_lux=0.0,
            uniformity=0.0,
            target_lux=target_lux,
            meets_target=False,
            sample_count=len(grid),
        )
    lux_per_cell = [
        sum(
            point_source_lux_at(f, p, work_plane_height_m=work_plane_height_m)
            for f in fixtures
        )
        for p in grid
    ]
    mean = sum(lux_per_cell) / len(lux_per_cell)
    min_lux = min(lux_per_cell)
    max_lux = max(lux_per_cell)
    uniformity = (min_lux / mean) if mean > 0 else 0.0
    return LuxStats(
        mean_lux=mean,
        min_lux=min_lux,
        max_lux=max_lux,
        uniformity=uniformity,
        target_lux=target_lux,
        meets_target=(mean >= _MEETS_TARGET_RATIO * target_lux),
        sample_count=len(grid),
    )
