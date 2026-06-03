"""Tests for the door-anchored polygon adjustment (#40)."""

from lighting_engine.models.geometry import Point, Room, RoomType
from lighting_engine.parser.door_anchor import anchor_polygons_to_doors
from lighting_engine.parser.door_detection import DoorRaw


def _square(name: str, cx: float, cy: float, side: float = 4.0) -> Room:
    s = side / 2
    return Room(
        id=name.lower(),
        name=name,
        type=RoomType.bedroom,
        polygon=[
            Point(x=cx - s, y=cy - s),
            Point(x=cx + s, y=cy - s),
            Point(x=cx + s, y=cy + s),
            Point(x=cx - s, y=cy + s),
        ],
        ceiling_height_m=2.7,
    )


def _door_at(x: float, y: float) -> DoorRaw:
    return DoorRaw(
        position=(x, y),
        swing_radius_m=None,
        swing_orientation_deg=None,
        source_layer="DOOR",
    )


def test_no_doors_means_no_change():
    room = _square("R", 0, 0)
    rooms, anchored = anchor_polygons_to_doors([room], [])
    assert anchored == 0
    assert rooms == [room]


def test_door_already_on_perimeter_no_translation():
    # Room from (-2, -2) to (2, 2); door at (2, 0) sits ON the east edge.
    room = _square("R", 0, 0)
    door = _door_at(2.0, 0.0)
    rooms, anchored = anchor_polygons_to_doors([room], [door])
    assert anchored == 0
    assert rooms[0].polygon == room.polygon


def test_door_just_within_threshold_no_translation():
    # Door 0.3m outside the east edge — within 0.4m, no move.
    room = _square("R", 0, 0)
    door = _door_at(2.3, 0.0)
    rooms, anchored = anchor_polygons_to_doors([room], [door])
    assert anchored == 0
    assert rooms[0].polygon == room.polygon


def test_door_off_perimeter_shifts_polygon_to_anchor_on_door():
    # Room from (-2, -2) to (2, 2); door at (2.0, 3.5) — 1.5m above the east
    # edge top corner. Closest perimeter point is (2, 2). Translation should
    # bring (2, 2) onto the door (2, 3.5) → shift by (0, 1.5).
    room = _square("R", 0, 0)
    door = _door_at(2.0, 3.5)
    rooms, anchored = anchor_polygons_to_doors([room], [door])
    assert anchored == 1
    # Polygon should now have all y values shifted by +1.5.
    new_ys = [p.y for p in rooms[0].polygon]
    assert min(new_ys) == -2 + 1.5
    assert max(new_ys) == 2 + 1.5


def test_polygon_size_is_preserved_after_anchor():
    room = _square("R", 0, 0, side=4.0)
    door = _door_at(2.0, 3.5)
    rooms, _anchored = anchor_polygons_to_doors([room], [door])
    xs = [p.x for p in rooms[0].polygon]
    ys = [p.y for p in rooms[0].polygon]
    assert (max(xs) - min(xs)) == 4.0
    assert (max(ys) - min(ys)) == 4.0


def test_door_anchor_allows_translation_with_no_overlap_risk():
    # Room A at (0, 0) side=4. Room B at (4.5, 0) side=4 — touching A's east
    # edge with a small gap. A door for A at (-3.5, 0) requires shifting A
    # west by 1.5. Room B stays out of the way.
    room_a = _square("A", 0, 0, side=4.0)
    room_b = _square("B", 4.5, 0, side=4.0)
    door = _door_at(-3.5, 0.0)
    rooms, anchored = anchor_polygons_to_doors([room_a, room_b], [door])
    assert anchored == 1
    # Room A moved west by 1.5
    xs = [p.x for p in rooms[0].polygon]
    assert min(xs) == -3.5
    assert max(xs) == 0.5
    # Room B unchanged
    assert rooms[1].polygon == room_b.polygon


def test_door_anchor_skipped_when_move_overlaps_other_room():
    # Room A at (0, 0) side=4 (bbox -2..2). Room B at (5, 0) side=4 (bbox
    # 3..7). 1m gap east of A. A door inside A at (-1.5, 0) — distance to
    # closest perimeter (west edge at x=-2) is 0.5m (> 0.4 trigger).
    # Shift = +0.5 east. A would move to bbox -1.5..2.5, overlapping B at
    # x in [3, 2.5] — wait, that's still no overlap because 2.5 < 3.
    # Use B center (4, 0), bbox 2..6. After shift A is at -1.5..2.5,
    # overlap with B = [2, 2.5] x [-2, 2] = 0.5*4 = 2 sqm. Originally A∩B
    # = [2, 2] = 0. Overlap increased by 2 → guard rejects.
    room_a = _square("A", 0, 0, side=4.0)
    room_b = _square("B", 4.0, 0, side=4.0)
    door = _door_at(-1.5, 0.0)
    rooms, anchored = anchor_polygons_to_doors([room_a, room_b], [door])
    assert anchored == 0
    # A unchanged
    assert rooms[0].polygon == room_a.polygon


def test_anchor_largest_offset_door_wins_when_multiple():
    # Room at (0, 0), bbox -2..2 on both axes. Two doors:
    #   - near: (2.5, 0) — 0.5m east of east edge midpoint
    #   - far: (0.0, 3.5) — 1.5m above north edge midpoint
    # The far door (offset 1.5) should drive the translation, not near (0.5).
    room = _square("R", 0, 0)
    near = _door_at(2.5, 0.0)
    far = _door_at(0.0, 3.5)
    rooms, anchored = anchor_polygons_to_doors([room], [near, far])
    assert anchored == 1
    ys = [p.y for p in rooms[0].polygon]
    # Shifted north by 1.5 (the larger offset)
    assert min(ys) == -0.5
    assert max(ys) == 3.5
