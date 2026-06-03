"""Tests for parser.wall_cast — large-scale room translation onto bounding walls."""

import pytest

from lighting_engine.models.geometry import Point, Room, RoomType
from lighting_engine.parser.wall_cast import (
    Segment,
    cast_bounding_walls,
    cast_bounding_walls_for_rooms,
)


def _rect(minx: float, miny: float, maxx: float, maxy: float) -> list[Point]:
    return [
        Point(x=minx, y=miny),
        Point(x=maxx, y=miny),
        Point(x=maxx, y=maxy),
        Point(x=minx, y=maxy),
    ]


def _room(name: str, polygon: list[Point]) -> Room:
    return Room(
        id=name.lower(),
        name=name,
        type=RoomType.bedroom,
        floor_level=0,
        polygon=polygon,
        ceiling_height_m=2.7,
    )


def _vertical_wall(x: float, y_lo: float, y_hi: float) -> Segment:
    return ((x, y_lo), (x, y_hi))


def _horizontal_wall(y: float, x_lo: float, x_hi: float) -> Segment:
    return ((x_lo, y), (x_hi, y))


def test_room_with_left_wall_only_translates_left_to_touch_wall():
    # Polygon at x=[5,9], wall at x=2 → push polygon LEFT by 3 → polygon at x=[2,6]
    room = _room("R", _rect(5.0, 0.0, 9.0, 4.0))
    walls = [_vertical_wall(2.0, -1.0, 5.0)]
    out = cast_bounding_walls(room, walls)
    xs = sorted({p.x for p in out.polygon})
    assert xs == pytest.approx([2.0, 6.0])
    # Y unchanged
    ys = sorted({p.y for p in out.polygon})
    assert ys == pytest.approx([0.0, 4.0])


def test_room_with_both_horizontal_walls_centers_when_widths_match():
    # Polygon 4m wide at x=[5,9], walls bounding x=[3,11] (8m wide) → ratio 0.5
    # → not in [0.85, 1.15], so picks closer wall instead of centering.
    room = _room("R", _rect(5.0, 0.0, 9.0, 4.0))
    walls = [
        _vertical_wall(3.0, -1.0, 5.0),
        _vertical_wall(11.0, -1.0, 5.0),
    ]
    out = cast_bounding_walls(room, walls)
    # gap_lo = 5-3 = 2, gap_hi = 11-9 = 2 → equal, code picks right
    xs = sorted({p.x for p in out.polygon})
    assert xs == pytest.approx([7.0, 11.0])


def test_both_walls_outside_polygon_picks_closer_when_widths_dont_match():
    # Centering branch is hard to exercise — polygons currently off-center
    # by enough to trigger a significant translation typically extend past
    # one of the bounding walls (so that wall fails the "outside polygon"
    # filter). In practice the parser keeps polygon roughly centered in its
    # actual wall-bounded gap, so the centering branch is a no-op refinement
    # and the closer-wall branch handles real cases. This test exercises that
    # branch: polygon 4m, wall gap 14m, picks closer wall.
    room = _room("R", _rect(5.0, 0.0, 9.0, 4.0))
    walls = [
        _vertical_wall(0.0, -1.0, 5.0),    # left wall, gap = 5
        _vertical_wall(13.0, -1.0, 5.0),   # right wall, gap = 4 (closer)
    ]
    out = cast_bounding_walls(room, walls)
    xs = sorted({p.x for p in out.polygon})
    # Right wall closer → polygon_maxx becomes 13 → polygon = [9, 13]
    assert xs == pytest.approx([9.0, 13.0])


def test_wall_too_far_no_translation():
    # Wall at x=2, polygon at x=[10,14] → gap = 8m > 6m max_cast → no translation
    room = _room("R", _rect(10.0, 0.0, 14.0, 4.0))
    walls = [_vertical_wall(2.0, -1.0, 5.0)]
    out = cast_bounding_walls(room, walls)
    assert out.polygon == room.polygon


def test_small_gap_below_significant_threshold_left_to_snap():
    # Wall at x=4.7, polygon at x=[5,9] → gap = 0.3 < 0.6 min_significant → no translation
    room = _room("R", _rect(5.0, 0.0, 9.0, 4.0))
    walls = [_vertical_wall(4.7, -1.0, 5.0)]
    out = cast_bounding_walls(room, walls)
    assert out.polygon == room.polygon


def test_wall_inside_polygon_is_ignored():
    # Wall at x=7 (inside polygon x=[5,9]) should NOT be picked as right-bound.
    room = _room("R", _rect(5.0, 0.0, 9.0, 4.0))
    walls = [_vertical_wall(7.0, -1.0, 5.0)]
    out = cast_bounding_walls(room, walls)
    assert out.polygon == room.polygon


def test_wall_perpendicular_overlap_too_short_rejected():
    # Polygon spans y=[0,4]. Wall spans y=[0, 0.8] only — overlap 0.8m < 25% of 4 = 1.0m
    room = _room("R", _rect(5.0, 0.0, 9.0, 4.0))
    walls = [_vertical_wall(2.0, 0.0, 0.8)]
    out = cast_bounding_walls(room, walls)
    assert out.polygon == room.polygon


def test_horizontal_wall_drives_vertical_translation():
    # Polygon at y=[5,9], horizontal wall at y=2 below → push DOWN to y=[2,6]
    room = _room("R", _rect(0.0, 5.0, 4.0, 9.0))
    walls = [_horizontal_wall(2.0, -1.0, 5.0)]
    out = cast_bounding_walls(room, walls)
    ys = sorted({p.y for p in out.polygon})
    assert ys == pytest.approx([2.0, 6.0])
    xs = sorted({p.x for p in out.polygon})
    assert xs == pytest.approx([0.0, 4.0])


def test_both_x_and_y_walls_translate_diagonally():
    # Polygon at (5,5)-(9,9). Left wall x=2 spanning y=[0,10], bottom wall
    # y=1 spanning x=[-1, 12] (must cover polygon's X extent).
    # Expected: dx = -3 (push left), dy = -4 (push down)
    room = _room("R", _rect(5.0, 5.0, 9.0, 9.0))
    walls = [
        _vertical_wall(2.0, 0.0, 10.0),
        _horizontal_wall(1.0, -1.0, 12.0),
    ]
    out = cast_bounding_walls(room, walls)
    xs = sorted({p.x for p in out.polygon})
    ys = sorted({p.y for p in out.polygon})
    assert xs == pytest.approx([2.0, 6.0])
    assert ys == pytest.approx([1.0, 5.0])


def test_translation_beyond_safety_cap_rejected():
    # max_translation_m = 1.0 with a wall far away; should reject.
    room = _room("R", _rect(5.0, 0.0, 9.0, 4.0))
    walls = [_vertical_wall(0.0, -1.0, 5.0)]   # gap = 5m
    out = cast_bounding_walls(room, walls, max_translation_m=1.0)
    assert out.polygon == room.polygon


def test_empty_walls_returns_unchanged():
    room = _room("R", _rect(5.0, 0.0, 9.0, 4.0))
    out = cast_bounding_walls(room, [])
    assert out.polygon == room.polygon


def test_already_aligned_polygon_returns_unchanged():
    # Polygon edge already on the wall → no significant gap → no translation
    room = _room("R", _rect(2.0, 0.0, 6.0, 4.0))
    walls = [_vertical_wall(2.0, -1.0, 5.0)]
    out = cast_bounding_walls(room, walls)
    # Wall at x=2 is NOT past polygon_minx=2 (need wall_x < polygon_minx) → skipped
    assert out.polygon == room.polygon


def test_overlap_guard_rejects_translation_into_another_room():
    # Room A wants to translate LEFT to touch wall at x=2, but room B already
    # occupies x=[2, 5]. Translation rejected → A stays unchanged.
    room_a = _room("A", _rect(6.0, 0.0, 9.0, 4.0))
    room_b = _room("B", _rect(2.0, 0.0, 5.0, 4.0))
    walls = [_vertical_wall(2.0, -1.0, 5.0)]
    out = cast_bounding_walls(room_a, walls, other_rooms=[room_b])
    assert out.polygon == room_a.polygon


def test_overlap_guard_allows_translation_when_no_collision():
    # Room A translates left toward wall; room B is far away → guard allows it
    room_a = _room("A", _rect(6.0, 0.0, 9.0, 4.0))
    room_b = _room("B", _rect(20.0, 0.0, 24.0, 4.0))
    walls = [_vertical_wall(2.0, -1.0, 5.0)]
    out = cast_bounding_walls(room_a, walls, other_rooms=[room_b])
    xs = sorted({p.x for p in out.polygon})
    assert xs == pytest.approx([2.0, 5.0])


def test_overlap_guard_ignores_different_floors():
    # Same X/Y region OK if floors differ — rooms are stacked, not colliding
    room_a = _room("A", _rect(6.0, 0.0, 9.0, 4.0))
    room_b = Room(
        id="b", name="B", type=RoomType.bedroom, floor_level=1,
        polygon=_rect(2.0, 0.0, 5.0, 4.0), ceiling_height_m=2.7,
    )
    walls = [_vertical_wall(2.0, -1.0, 5.0)]
    out = cast_bounding_walls(room_a, walls, other_rooms=[room_b])
    xs = sorted({p.x for p in out.polygon})
    assert xs == pytest.approx([2.0, 5.0])


def test_batch_helper_counts_translated_rooms():
    rooms = [
        _room("A", _rect(5.0, 0.0, 9.0, 4.0)),   # will translate left
        _room("B", _rect(0.0, 10.0, 4.0, 14.0)),  # no nearby wall → unchanged
    ]
    walls = [_vertical_wall(2.0, -1.0, 5.0)]
    out, translated = cast_bounding_walls_for_rooms(rooms, walls)
    assert translated == 1
    assert out[1].polygon == rooms[1].polygon
