from lighting_engine.lighting.standards import get_lux_standard
from lighting_engine.models.geometry import RoomType


def test_every_room_type_has_a_lux_standard():
    for rt in RoomType:
        standard = get_lux_standard(rt)
        assert standard.cct_k >= 2200
        assert standard.cri_min >= 70


def test_outdoor_and_staircase_skip_ambient_placement():
    assert get_lux_standard(RoomType.outdoor).place_ambient is False
    assert get_lux_standard(RoomType.staircase).place_ambient is False


def test_indian_residential_defaults_skew_warm():
    # Living, dining, bedroom should be 2700K (warm) — Indian residential standard
    assert get_lux_standard(RoomType.living).cct_k == 2700
    assert get_lux_standard(RoomType.dining).cct_k == 2700
    assert get_lux_standard(RoomType.bedroom).cct_k == 2700


def test_task_rooms_get_cooler_cct():
    assert get_lux_standard(RoomType.kitchen).cct_k >= 3000
    assert get_lux_standard(RoomType.study).cct_k >= 3000
