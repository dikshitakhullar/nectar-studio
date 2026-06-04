"""Tests for door-destination inference (Phase A).

The inference walks each room's doors, computes the door's (x, y) on the
room's polygon edge, steps a short distance along the wall's outward normal,
then asks which OTHER room's polygon contains that exterior point. That room
becomes the door's destination.

Doors on exterior walls (no adjacent room) stay with `destination_room_id = None`.
"""

from pathlib import Path

from lighting_engine.models.geometry import Door, Point, Room, RoomType
from lighting_engine.parser.door_destinations import infer_door_destinations
from lighting_engine.parser.pipeline import parse_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


def _square_room(
    *,
    name: str,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    room_type: RoomType = RoomType.bedroom,
) -> Room:
    """Square room ordered counter-clockwise so wall_index 0..3 = S, E, N, W.

    Polygon vertices (counter-clockwise from bottom-left):
      0: (xmin, ymin)  bottom-left
      1: (xmax, ymin)  bottom-right
      2: (xmax, ymax)  top-right
      3: (xmin, ymax)  top-left

    Edges:
      0: 0 → 1 (bottom / south, outward normal points -y)
      1: 1 → 2 (right / east,  outward normal points +x)
      2: 2 → 3 (top / north,   outward normal points +y)
      3: 3 → 0 (left / west,   outward normal points -x)
    """
    return Room(
        id=name.lower().replace(" ", "_"),
        name=name,
        type=room_type,
        polygon=[
            Point(x=xmin, y=ymin),
            Point(x=xmax, y=ymin),
            Point(x=xmax, y=ymax),
            Point(x=xmin, y=ymax),
        ],
        ceiling_height_m=2.7,
    )


def test_door_on_shared_wall_infers_neighbour_destination():
    """Two rooms abut along x = 5; door on bedroom's east wall should point
    to the dining room (its eastern neighbour)."""
    bedroom = _square_room(name="Bedroom", xmin=0, ymin=0, xmax=5, ymax=5)
    dining = _square_room(
        name="Dining", xmin=5, ymin=0, xmax=10, ymax=5,
        room_type=RoomType.dining,
    )
    # Door on bedroom's east wall (wall_index = 1), midway up
    bedroom.doors.append(Door(
        id="door-bed-east",
        wall_index=1,
        along_wall=0.5,
        width_m=0.9,
    ))

    infer_door_destinations([bedroom, dining])

    assert bedroom.doors[0].destination_room_id == "dining"


def test_door_on_exterior_wall_has_no_destination():
    """Door on the south wall of a single room with no neighbour stays None."""
    bedroom = _square_room(name="Bedroom", xmin=0, ymin=0, xmax=5, ymax=5)
    bedroom.doors.append(Door(
        id="door-bed-south",
        wall_index=0,  # south wall, no room below
        along_wall=0.5,
        width_m=0.9,
    ))

    infer_door_destinations([bedroom])

    assert bedroom.doors[0].destination_room_id is None


def test_door_with_no_wall_index_is_skipped():
    """Doors the parser couldn't snap (wall_index=None) leave destination None."""
    bedroom = _square_room(name="Bedroom", xmin=0, ymin=0, xmax=5, ymax=5)
    bedroom.doors.append(Door(
        id="door-unknown",
        wall_index=None,
        along_wall=None,
        width_m=0.9,
    ))

    infer_door_destinations([bedroom])

    assert bedroom.doors[0].destination_room_id is None


def test_door_destinations_does_not_assign_door_to_own_room():
    """A door is never inferred to lead to its own host room."""
    bedroom = _square_room(name="Bedroom", xmin=0, ymin=0, xmax=5, ymax=5)
    bedroom.doors.append(Door(
        id="door-self",
        wall_index=2,  # north wall, no neighbour
        along_wall=0.5,
        width_m=0.9,
    ))

    infer_door_destinations([bedroom])

    assert bedroom.doors[0].destination_room_id is None


def test_multiple_doors_on_shared_walls_get_independent_destinations():
    """A room with doors on two distinct walls, each leading to a different
    neighbour."""
    # Layout: bedroom centre with east -> dining, west -> hallway
    hallway = _square_room(
        name="Hallway", xmin=-5, ymin=0, xmax=0, ymax=5,
        room_type=RoomType.hallway,
    )
    bedroom = _square_room(name="Bedroom", xmin=0, ymin=0, xmax=5, ymax=5)
    dining = _square_room(
        name="Dining", xmin=5, ymin=0, xmax=10, ymax=5,
        room_type=RoomType.dining,
    )
    bedroom.doors.append(Door(
        id="door-east", wall_index=1, along_wall=0.5, width_m=0.9,
    ))
    bedroom.doors.append(Door(
        id="door-west", wall_index=3, along_wall=0.5, width_m=0.9,
    ))

    infer_door_destinations([hallway, bedroom, dining])

    east_door = next(d for d in bedroom.doors if d.id == "door-east")
    west_door = next(d for d in bedroom.doors if d.id == "door-west")
    assert east_door.destination_room_id == "dining"
    assert west_door.destination_room_id == "hallway"


def test_destination_inference_is_idempotent():
    """Re-running the inference doesn't change already-set destinations."""
    bedroom = _square_room(name="Bedroom", xmin=0, ymin=0, xmax=5, ymax=5)
    dining = _square_room(
        name="Dining", xmin=5, ymin=0, xmax=10, ymax=5,
        room_type=RoomType.dining,
    )
    bedroom.doors.append(Door(
        id="door-east", wall_index=1, along_wall=0.5, width_m=0.9,
    ))
    infer_door_destinations([bedroom, dining])
    first = bedroom.doors[0].destination_room_id
    infer_door_destinations([bedroom, dining])
    assert bedroom.doors[0].destination_room_id == first


def test_destination_room_id_default_is_none():
    """The new Door field defaults to None — backwards-compatible."""
    door = Door(id="d", width_m=0.9)
    assert door.destination_room_id is None


def test_delhi_fixture_infers_multiple_door_destinations():
    """On the bundled Delhi fixture, at least 3 doors should be inferred to
    connect to a non-None destination room (kitchen ↔ dining, etc.)."""
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="Delhi door-destination smoke",
    )
    doors_with_dest: list[tuple[str, str]] = []
    for room in project.rooms:
        for door in room.doors:
            if door.destination_room_id is not None:
                doors_with_dest.append((room.name, door.destination_room_id))
    assert len(doors_with_dest) >= 3, (
        f"Expected ≥3 doors with a destination on Delhi fixture; "
        f"got {len(doors_with_dest)}: {doors_with_dest}"
    )
