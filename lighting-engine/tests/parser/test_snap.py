"""Tests for the wall-snap pass: room polygon edges snap to nearby wall lines.

All coordinates here are in the local-meter frame (matching the Room polygon
convention). Each test constructs a tiny synthetic world (room polygon + wall
segments) and checks the snap behaviour for one specific situation.
"""

import pytest

from lighting_engine.models.geometry import Point, Room, RoomType
from lighting_engine.parser.snap import Segment, snap_room_to_walls


def _rect_room(
    room_id: str,
    x_min: float, y_min: float, x_max: float, y_max: float,
) -> Room:
    """Construct an axis-aligned rectangular Room at the given bounds (meters)."""
    return Room(
        id=room_id,
        name=room_id.upper(),
        type=RoomType.bedroom,
        polygon=[
            Point(x=x_min, y=y_min),
            Point(x=x_max, y=y_min),
            Point(x=x_max, y=y_max),
            Point(x=x_min, y=y_max),
        ],
        ceiling_height_m=2.7,
    )


def _bbox(room: Room) -> tuple[float, float, float, float]:
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def test_single_room_with_nearby_wall_snaps_edge_to_wall():
    """A polygon whose right edge sits 0.3m away from a vertical wall should
    snap that edge onto the wall's X coordinate."""
    # 4m × 3m room from (0,0) to (4,3); wall is a vertical line at x=4.3
    room = _rect_room("r1", 0.0, 0.0, 4.0, 3.0)
    walls: list[Segment] = [((4.3, -0.5), (4.3, 3.5))]

    snapped = snap_room_to_walls(room, walls)

    x_min, y_min, x_max, y_max = _bbox(snapped)
    # Right edge snapped to x=4.3
    assert x_max == pytest.approx(4.3, abs=1e-9)
    # Left edge unchanged (no wall on that side)
    assert x_min == pytest.approx(0.0, abs=1e-9)
    # Y bounds preserved (no top/bottom walls)
    assert y_min == pytest.approx(0.0, abs=1e-9)
    assert y_max == pytest.approx(3.0, abs=1e-9)


def test_two_rooms_sharing_a_wall_snap_to_the_same_line():
    """Two adjacent rooms whose right/left edges both sit near the same wall
    should both snap to the same X coordinate — the phantom gap disappears."""
    # Left room: (0,0)-(3.9, 3); Right room: (4.1, 0)-(7, 3); shared wall at x=4.0
    left = _rect_room("left", 0.0, 0.0, 3.9, 3.0)
    right = _rect_room("right", 4.1, 0.0, 7.0, 3.0)
    walls: list[Segment] = [((4.0, -0.5), (4.0, 3.5))]

    new_left = snap_room_to_walls(left, walls)
    new_right = snap_room_to_walls(right, walls)

    _, _, left_xmax, _ = _bbox(new_left)
    right_xmin, _, _, _ = _bbox(new_right)
    assert left_xmax == pytest.approx(4.0, abs=1e-9)
    assert right_xmin == pytest.approx(4.0, abs=1e-9)
    # And they coincide — gap eliminated
    assert left_xmax == pytest.approx(right_xmin, abs=1e-9)


def test_wall_too_far_does_not_snap():
    """A wall more than max_perp_dist_m away should not pull the edge."""
    room = _rect_room("r1", 0.0, 0.0, 4.0, 3.0)
    # Wall sits 1.5m to the right of the edge — beyond the 0.8m default
    walls: list[Segment] = [((5.5, -0.5), (5.5, 3.5))]

    snapped = snap_room_to_walls(room, walls)

    # Nothing should have moved
    assert snapped.polygon == room.polygon


def test_wall_not_parallel_does_not_snap():
    """A wall whose direction makes >15° with the edge should not be a candidate.

    Here the polygon's right edge is vertical; the only nearby wall is
    diagonal (~45° off vertical), so no snap.
    """
    room = _rect_room("r1", 0.0, 0.0, 4.0, 3.0)
    # Diagonal wall passing through (4.3, 1.5) at ~45°
    walls: list[Segment] = [((3.8, 1.0), (4.8, 2.0))]

    snapped = snap_room_to_walls(room, walls)

    assert snapped.polygon == room.polygon


def test_area_deformation_guard_rejects_snap():
    """If snapping would deform the polygon's area beyond the 15% guard, the
    snap is rejected and the room returned unchanged.

    Here we surround a 4m × 3m room (area 12 sqm) with walls placed so that
    snapping shrinks the polygon dramatically — both opposite sides snap
    inward by ~0.7m, pinching width from 4m → ~2.6m → area drops 35%.
    """
    room = _rect_room("r1", 0.0, 0.0, 4.0, 3.0)
    walls: list[Segment] = [
        # Left wall pulled inward to x=0.7
        ((0.7, -0.5), (0.7, 3.5)),
        # Right wall pulled inward to x=3.3
        ((3.3, -0.5), (3.3, 3.5)),
    ]

    snapped = snap_room_to_walls(room, walls)

    # Guard rejects the snap → polygon unchanged
    assert snapped.polygon == room.polygon


def test_low_overlap_wall_does_not_snap():
    """A wall that only barely overlaps the edge (≪50%) is not a candidate.

    The room's bottom edge runs from (0,0) to (4,0). A nearby horizontal wall
    that only covers x ∈ [0, 1] (25% of the edge) should not snap.
    """
    room = _rect_room("r1", 0.0, 0.0, 4.0, 3.0)
    walls: list[Segment] = [((0.0, -0.3), (1.0, -0.3))]

    snapped = snap_room_to_walls(room, walls)

    assert snapped.polygon == room.polygon


def test_snap_disabled_when_no_walls():
    """Empty wall list → polygon unchanged."""
    room = _rect_room("r1", 0.0, 0.0, 4.0, 3.0)
    snapped = snap_room_to_walls(room, [])
    assert snapped.polygon == room.polygon


def test_snap_preserves_polygon_when_already_on_wall():
    """If a polygon edge already coincides with a wall, snapping is a no-op
    (the projection of a point onto the line it already lies on is itself).
    """
    room = _rect_room("r1", 0.0, 0.0, 4.0, 3.0)
    walls: list[Segment] = [((4.0, -0.5), (4.0, 3.5))]

    snapped = snap_room_to_walls(room, walls)

    x_min, y_min, x_max, y_max = _bbox(snapped)
    assert x_min == pytest.approx(0.0, abs=1e-9)
    assert x_max == pytest.approx(4.0, abs=1e-9)
    assert y_min == pytest.approx(0.0, abs=1e-9)
    assert y_max == pytest.approx(3.0, abs=1e-9)
