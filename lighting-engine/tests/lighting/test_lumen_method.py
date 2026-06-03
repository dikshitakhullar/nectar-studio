from lighting_engine.lighting.lumen_method import (
    fixture_count_for_room,
    required_lumens,
    spacing_m,
)


def test_required_lumens_basic_formula():
    # 200 lux × 20 sqm / (0.6 × 0.8) = 4000 / 0.48 ≈ 8333.333 lm
    result = required_lumens(target_lux=200, area_sqm=20)
    assert abs(result - (4000.0 / 0.48)) < 1e-6


def test_required_lumens_zero_when_inputs_invalid():
    assert required_lumens(target_lux=0, area_sqm=20) == 0.0
    assert required_lumens(target_lux=200, area_sqm=0) == 0.0


def test_fixture_count_for_typical_living_room():
    # 4×5m living (20 sqm), target 150 lux, 1500lm fixture
    # required = 150 × 20 / (0.6 × 0.8) = 3000 / 0.48 = 6250 lm
    # → ceil(6250 / 1500) = ceil(4.167) = 5 fixtures
    count = fixture_count_for_room(
        target_lux=150, area_sqm=20.0, fixture_lumens=1500.0,
    )
    assert count == 5


def test_fixture_count_for_tiny_bathroom():
    # 2×2m bath (4 sqm), target 200 lux, 1500lm fixture
    # required = 200 × 4 / (0.6 × 0.8) = 800 / 0.48 ≈ 1666.67 lm
    # → ceil(1666.67 / 1500) = ceil(1.111) = 2 fixtures
    count = fixture_count_for_room(
        target_lux=200, area_sqm=4.0, fixture_lumens=1500.0,
    )
    assert count == 2


def test_fixture_count_floor_is_one_when_target_positive():
    # Even a tiny room with a target should get at least 1 fixture
    count = fixture_count_for_room(
        target_lux=100, area_sqm=1.5, fixture_lumens=1500.0,
    )
    assert count >= 1


def test_fixture_count_zero_when_no_target():
    # Outdoor / staircase rooms have target=0 → 0 fixtures
    assert fixture_count_for_room(target_lux=0, area_sqm=20, fixture_lumens=1500) == 0


def test_spacing_uses_smh_ratio():
    # 2.7m ceiling, S/MH=1.5, work plane 0.8m
    # MH = 2.7 - 0.8 = 1.9; spacing = 1.5 × 1.9 = 2.85
    assert abs(spacing_m(s_mh_ratio=1.5, ceiling_height_m=2.7) - 2.85) < 1e-6
