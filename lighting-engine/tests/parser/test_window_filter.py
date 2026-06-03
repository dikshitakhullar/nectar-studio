"""Tests for window_filter: a window only counts when it sits on an interior
room's wall.

Each test builds a tiny synthetic world (one or two rooms + one window
segment) and checks whether the filter keeps or drops the window. All
coordinates are in the local-meter frame.
"""

from lighting_engine.models.geometry import Point, Room, RoomType
from lighting_engine.parser.snap import Segment
from lighting_engine.parser.window_filter import (
    _is_interior_room,
    filter_valid_windows,
)


def _rect_room(
    room_id: str,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    *,
    name: str | None = None,
    room_type: RoomType = RoomType.bedroom,
) -> Room:
    """Construct an axis-aligned rectangular Room at the given bounds (meters)."""
    return Room(
        id=room_id,
        name=name if name is not None else room_id.upper(),
        type=room_type,
        polygon=[
            Point(x=x_min, y=y_min),
            Point(x=x_max, y=y_min),
            Point(x=x_max, y=y_max),
            Point(x=x_min, y=y_max),
        ],
        ceiling_height_m=2.7,
    )


# ----- _is_interior_room ---------------------------------------------------


def test_is_interior_room_bedroom_is_interior():
    assert _is_interior_room(_rect_room("r", 0, 0, 4, 3))


def test_is_interior_room_outdoor_type_is_not_interior():
    assert not _is_interior_room(
        _rect_room("r", 0, 0, 4, 3, room_type=RoomType.outdoor)
    )


def test_is_interior_room_staircase_type_is_not_interior():
    assert not _is_interior_room(
        _rect_room("r", 0, 0, 4, 3, room_type=RoomType.staircase)
    )


def test_is_interior_room_terrace_name_is_not_interior():
    # Even when the room is mis-typed as `unknown`, a TERRACE name marks it
    # as outdoors for the window check.
    assert not _is_interior_room(
        _rect_room("r", 0, 0, 4, 3, name="TERRACE", room_type=RoomType.unknown)
    )


def test_is_interior_room_balcony_name_is_not_interior():
    assert not _is_interior_room(
        _rect_room("r", 0, 0, 4, 3, name="Balcony 1", room_type=RoomType.unknown)
    )


def test_is_interior_room_match_is_case_insensitive():
    assert not _is_interior_room(
        _rect_room("r", 0, 0, 4, 3, name="terrace", room_type=RoomType.unknown)
    )


# ----- filter_valid_windows ------------------------------------------------


def test_window_on_interior_room_edge_is_kept():
    """A window sitting on the right edge of an interior room is a real window."""
    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    # Window flush with the right wall (x=4), covering most of it vertically
    window: Segment = ((4.0, 0.5), (4.0, 2.5))

    kept, dropped = filter_valid_windows([window], [room])

    assert kept == [window]
    assert dropped == []


def test_window_floating_inside_interior_room_is_dropped():
    """A window in the middle of the room, not on any wall, is bogus."""
    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    # Free-floating segment somewhere inside the room
    window: Segment = ((1.5, 1.5), (2.5, 1.5))

    kept, dropped = filter_valid_windows([window], [room])

    assert kept == []
    assert dropped == [window]


def test_window_on_outdoor_room_edge_is_dropped():
    """A window on a TERRACE (outdoor) room's edge is parapet detail, not a window."""
    terrace = _rect_room(
        "terr", 0.0, 0.0, 4.0, 3.0, name="TERRACE", room_type=RoomType.outdoor,
    )
    window: Segment = ((4.0, 0.5), (4.0, 2.5))

    kept, dropped = filter_valid_windows([window], [terrace])

    assert kept == []
    assert dropped == [window]


def test_window_on_staircase_room_edge_is_dropped():
    """Staircases don't have windows in our model — drop them."""
    stair = _rect_room(
        "st", 0.0, 0.0, 4.0, 3.0, name="STAIRCASE", room_type=RoomType.staircase,
    )
    window: Segment = ((4.0, 0.5), (4.0, 2.5))

    kept, dropped = filter_valid_windows([window], [stair])

    assert kept == []
    assert dropped == [window]


def test_window_on_terrace_named_room_dropped_even_if_typed_unknown():
    """Catch terraces by name when the parser hasn't typed them as outdoor."""
    terrace = _rect_room(
        "t", 0.0, 0.0, 4.0, 3.0, name="TERRACE", room_type=RoomType.unknown,
    )
    window: Segment = ((4.0, 0.5), (4.0, 2.5))

    kept, dropped = filter_valid_windows([window], [terrace])

    assert kept == []
    assert dropped == [window]


def test_window_within_perp_tolerance_is_kept():
    """A window sitting just inside the perp-distance tolerance is still kept.

    Default max_perp = 0.4m. The room's right edge is at x=4; window sits
    at x=4.3 (0.3m away → within tolerance).
    """
    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    window: Segment = ((4.3, 0.5), (4.3, 2.5))

    kept, dropped = filter_valid_windows([window], [room])

    assert kept == [window]
    assert dropped == []


def test_window_beyond_perp_tolerance_is_dropped():
    """A window further than max_perp from the nearest wall is dropped."""
    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    # 0.6m away from the right edge — beyond the 0.4m default tolerance
    window: Segment = ((4.6, 0.5), (4.6, 2.5))

    kept, dropped = filter_valid_windows([window], [room])

    assert kept == []
    assert dropped == [window]


def test_window_parallel_tolerance_edge_case_within_15_deg_is_kept():
    """A window angled ~10° off the wall's direction is still a parallel match.

    Room's right edge runs vertically (along +y). Window runs from (4.0, 0.5)
    to (4.0 + sin(10°)·2, 0.5 + cos(10°)·2) — ~10° off vertical, well within
    the 15° tolerance.
    """
    import math

    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    angle_rad = math.radians(10.0)
    length = 2.0
    end_x = 4.0 + math.sin(angle_rad) * length
    end_y = 0.5 + math.cos(angle_rad) * length
    window: Segment = ((4.0, 0.5), (end_x, end_y))

    kept, dropped = filter_valid_windows([window], [room])

    assert kept == [window]
    assert dropped == []


def test_window_parallel_tolerance_beyond_15_deg_is_dropped():
    """A window angled ~30° off the wall direction is NOT parallel enough."""
    import math

    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    # Start on the right wall, but angle the window 30° off vertical
    angle_rad = math.radians(30.0)
    length = 2.0
    end_x = 4.0 + math.sin(angle_rad) * length
    end_y = 0.5 + math.cos(angle_rad) * length
    window: Segment = ((4.0, 0.5), (end_x, end_y))

    kept, dropped = filter_valid_windows([window], [room])

    assert kept == []
    assert dropped == [window]


def test_window_with_too_little_overlap_is_dropped():
    """A short window that hangs off the end of a wall (<50% overlap) is dropped.

    Room's right edge runs y ∈ [0, 3]. Window is a 2m segment from y=2.5 to
    y=4.5 — only 0.5m (25% of its length) overlaps the room edge.
    """
    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    window: Segment = ((4.0, 2.5), (4.0, 4.5))

    kept, dropped = filter_valid_windows([window], [room])

    assert kept == []
    assert dropped == [window]


def test_kept_when_interior_room_among_outdoor_rooms():
    """Mixed room list: window adjacent to the one interior room is kept."""
    terrace = _rect_room(
        "t", 0.0, 0.0, 4.0, 3.0, name="TERRACE", room_type=RoomType.outdoor,
    )
    bedroom = _rect_room("b", 5.0, 0.0, 9.0, 3.0, name="BEDROOM")
    # Window on bedroom's left wall (x=5)
    window: Segment = ((5.0, 0.5), (5.0, 2.5))

    kept, dropped = filter_valid_windows([window], [terrace, bedroom])

    assert kept == [window]
    assert dropped == []


def test_empty_window_list_returns_empty():
    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    kept, dropped = filter_valid_windows([], [room])
    assert kept == []
    assert dropped == []


def test_empty_rooms_list_drops_all_windows():
    """No rooms → nothing can be on an interior wall → all windows dropped."""
    window: Segment = ((4.0, 0.5), (4.0, 2.5))
    kept, dropped = filter_valid_windows([window], [])
    assert kept == []
    assert dropped == [window]


def test_no_interior_rooms_drops_all_windows():
    """All rooms are outdoor → no valid wall to host any window."""
    terrace = _rect_room(
        "t", 0.0, 0.0, 4.0, 3.0, name="TERRACE", room_type=RoomType.outdoor,
    )
    window: Segment = ((4.0, 0.5), (4.0, 2.5))
    kept, dropped = filter_valid_windows([window], [terrace])
    assert kept == []
    assert dropped == [window]


def test_degenerate_zero_length_window_is_dropped():
    """A zero-length segment can never overlap an edge — drop it."""
    room = _rect_room("bed", 0.0, 0.0, 4.0, 3.0)
    window: Segment = ((4.0, 1.5), (4.0, 1.5))
    kept, dropped = filter_valid_windows([window], [room])
    assert kept == []
    assert dropped == [window]
