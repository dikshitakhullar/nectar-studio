from lighting_engine.parser.geometry import PlanRegion, find_plan_region


def test_single_cluster_returns_its_bbox():
    pts = [(211300.0, -106000.0), (212000.0, -105000.0),
           (214000.0, -103000.0), (213500.0, -104500.0)]
    region = find_plan_region(pts)
    assert isinstance(region, PlanRegion)
    assert region.min_x == 211300.0
    assert region.max_x == 214000.0
    assert region.width == 2700.0


def test_strays_far_from_cluster_are_rejected():
    # 4 cluster points around 211–214k, 2 strays at 0 and 347000
    pts = [
        (211300.0, -106000.0), (212000.0, -105000.0),
        (214000.0, -103000.0), (213500.0, -104500.0),
        (-16.0, -100000.0),                       # stray near origin
        (347000.0, -100000.0),                    # stray far right
    ]
    region = find_plan_region(pts)
    assert region.min_x >= 211000.0
    assert region.max_x <= 215000.0
    assert region.outliers_rejected == 2


def test_empty_input_raises():
    import pytest
    with pytest.raises(ValueError):
        find_plan_region([])


def test_region_contains_point():
    pts = [(0.0, 0.0), (10.0, 10.0)]
    region = find_plan_region(pts)
    assert region.contains((5.0, 5.0))
    assert not region.contains((20.0, 20.0))
