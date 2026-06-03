from lighting_engine.lighting.grid import compute_ambient_grid
from lighting_engine.models.geometry import Point


def _rect(w: float, h: float) -> list[Point]:
    return [Point(x=0, y=0), Point(x=w, y=0), Point(x=w, y=h), Point(x=0, y=h)]


def test_grid_has_requested_count_for_simple_rectangle():
    positions = compute_ambient_grid(_rect(6.0, 8.0), fixture_count=12)
    assert len(positions) == 12


def test_grid_lays_out_as_cols_x_rows():
    # 6×8m room, 12 fixtures → expect 3×4 grid (cols×rows, matching aspect)
    positions = compute_ambient_grid(_rect(6.0, 8.0), fixture_count=12)
    xs = sorted({round(p.x, 3) for p in positions})
    ys = sorted({round(p.y, 3) for p in positions})
    assert len(xs) == 3
    assert len(ys) == 4


def test_grid_positions_have_perimeter_offset():
    # 4×4m room, 4 fixtures → 2×2 grid; fixtures should be inset from walls
    positions = compute_ambient_grid(_rect(4.0, 4.0), fixture_count=4)
    # First column at x = step/2 = 1.0; last at x = 3.0
    xs = sorted({round(p.x, 3) for p in positions})
    assert xs == [1.0, 3.0]


def test_grid_zero_count_returns_empty():
    assert compute_ambient_grid(_rect(4.0, 4.0), fixture_count=0) == []


def test_max_spacing_can_add_fixtures():
    # 8×8m room, ask for 4 fixtures (2×2 grid) but cap spacing at 3m
    # Without cap: 4m spacing. With cap: must split further → at least 9 (3×3)
    positions = compute_ambient_grid(
        _rect(8.0, 8.0), fixture_count=4, max_spacing_m=3.0,
    )
    assert len(positions) >= 9


def test_all_grid_positions_lie_inside_polygon():
    positions = compute_ambient_grid(_rect(4.0, 6.0), fixture_count=6)
    for p in positions:
        assert 0 < p.x < 4
        assert 0 < p.y < 6
