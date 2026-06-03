"""Tests for the point-source lux model + grid uniformity stats."""

import pytest

from lighting_engine.lux.uniformity import point_source_lux_at
from lighting_engine.models.geometry import Fixture, FixtureSource, Point


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
