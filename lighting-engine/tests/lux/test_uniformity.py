"""Tests for the point-source lux model + grid uniformity stats."""

import pytest

from lighting_engine.lux.uniformity import LuxStats, compute_uniformity, point_source_lux_at
from lighting_engine.models.geometry import Fixture, FixtureSource, Point, Room, RoomType


def _down_fixture(x: float, y: float, lumens: float = 1500.0) -> Fixture:
    return Fixture(
        id="f",
        type="downlight",
        position=Point(x=x, y=y),
        mount_height_m=2.7,
        source=FixtureSource.proposed,
        lumens=lumens,
        wattage_w=12,
        cct_k=2700,
        cri=90,
        beam_angle_deg=60.0,
    )


def test_lux_directly_below_fixture_uses_full_intensity() -> None:
    """Lux directly below a 1500lm fixture (60 deg beam, 2.7m mount) at the work plane."""
    fixture = _down_fixture(0, 0)
    lux = point_source_lux_at(fixture, Point(x=0, y=0), work_plane_height_m=0.8)
    # vertical distance = 2.7 - 0.8 = 1.9m, theta=0, cos(0)=1
    # candela = lumens / solid_angle_for_60deg approx 1500 / 0.842 approx 1782
    # E = candela * 1 / 1.9^2 approx 493 lux
    assert lux == pytest.approx(493, abs=10)


def test_lux_decays_with_distance() -> None:
    """A point 2m away from directly-below should receive less lux."""
    fixture = _down_fixture(0, 0)
    near = point_source_lux_at(fixture, Point(x=0, y=0), work_plane_height_m=0.8)
    far = point_source_lux_at(fixture, Point(x=2, y=0), work_plane_height_m=0.8)
    assert far < near
    assert far >= 0


def test_lux_outside_beam_cone_is_zero() -> None:
    """Point well outside a 60 deg beam cone gets near-zero contribution."""
    fixture = _down_fixture(0, 0)
    # 60 deg full beam from 1.9m height -> radius approx 1.9 * tan(30 deg) approx 1.1m
    lux = point_source_lux_at(fixture, Point(x=5, y=0), work_plane_height_m=0.8)
    assert lux == pytest.approx(0, abs=1)


def test_lux_when_mount_height_is_none_defaults_to_27m() -> None:
    """A ceiling-mounted fixture (mount_height_m=None) should default to 2.7m."""
    fixture = Fixture(
        id="f",
        type="downlight",
        position=Point(x=0, y=0),
        mount_height_m=None,
        source=FixtureSource.proposed,
        lumens=1500.0,
        wattage_w=12,
        cct_k=2700,
        cri=90,
        beam_angle_deg=60.0,
    )
    lux = point_source_lux_at(fixture, Point(x=0, y=0), work_plane_height_m=0.8)
    # Same result as the explicit-2.7m case above.
    assert lux == pytest.approx(493, abs=10)


def test_lux_when_work_plane_above_mount_height_is_zero() -> None:
    """If the work plane is above the fixture, contribution collapses to zero."""
    fixture = _down_fixture(0, 0)
    lux = point_source_lux_at(fixture, Point(x=0, y=0), work_plane_height_m=3.0)
    assert lux == 0.0


# ---------------------------------------------------------------------------
# Task 5.2 — grid sampler + LuxStats + compute_uniformity
# ---------------------------------------------------------------------------


def _square_room(side: float) -> Room:
    s = side / 2
    return Room(
        id="r",
        name="R",
        type=RoomType.living,
        floor_level=0,
        polygon=[
            Point(x=-s, y=-s),
            Point(x=s, y=-s),
            Point(x=s, y=s),
            Point(x=-s, y=s),
        ],
        ceiling_height_m=2.7,
    )


def test_uniformity_with_single_fixture_is_low() -> None:
    room = _square_room(4.0)
    fixtures = [_down_fixture(0, 0)]
    stats = compute_uniformity(room, fixtures, target_lux=200.0)
    assert isinstance(stats, LuxStats)
    assert stats.mean_lux > 0
    assert stats.min_lux >= 0
    assert stats.max_lux >= stats.mean_lux
    # One fixture in the centre -> uniformity is poor (corners get nothing).
    assert stats.uniformity < 0.4


def test_uniformity_with_grid_of_fixtures_is_high() -> None:
    room = _square_room(4.0)
    single = compute_uniformity(room, [_down_fixture(0, 0)], target_lux=200.0)
    # 3x3 grid of fixtures.
    fixtures = [
        _down_fixture(x, y)
        for x in (-1.0, 0.0, 1.0)
        for y in (-1.0, 0.0, 1.0)
    ]
    stats = compute_uniformity(room, fixtures, target_lux=200.0)
    # A grid should be markedly more uniform than the single-fixture baseline.
    assert stats.uniformity > single.uniformity
    assert stats.uniformity > 0.3
    assert stats.mean_lux > 150


def test_uniformity_meets_target_flag() -> None:
    room = _square_room(4.0)
    fixtures = [
        _down_fixture(x, y, lumens=2500)
        for x in (-1.0, 0.0, 1.0)
        for y in (-1.0, 0.0, 1.0)
    ]
    stats = compute_uniformity(room, fixtures, target_lux=200.0)
    assert stats.target_lux == 200.0
    assert stats.meets_target is True


def test_uniformity_with_no_fixtures_returns_zeros() -> None:
    room = _square_room(4.0)
    stats = compute_uniformity(room, [], target_lux=200.0)
    assert stats.mean_lux == 0.0
    assert stats.min_lux == 0.0
    assert stats.max_lux == 0.0
    assert stats.uniformity == 0.0
    assert stats.meets_target is False


def test_uniformity_samples_only_points_inside_polygon() -> None:
    """L-shaped room: grid must skip the cut-out corner."""
    # L-shape: 4x4 square with the upper-right 2x2 corner removed.
    room = Room(
        id="L",
        name="L",
        type=RoomType.living,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=4, y=0),
            Point(x=4, y=2),
            Point(x=2, y=2),
            Point(x=2, y=4),
            Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
    )
    # Place a fixture inside the L so we get some non-zero samples.
    fixtures = [_down_fixture(1.0, 1.0)]
    stats = compute_uniformity(room, fixtures, target_lux=200.0)
    # Full 4x4 bbox at 0.5m step has 8x8 = 64 cells; the L removes the
    # upper-right 2x2 quadrant = 16 cells, so the sampler should report 48.
    assert stats.sample_count == 48
