from pathlib import Path

from lighting_engine.digest import compute_digest
from lighting_engine.digest.models import WallOrientation
from lighting_engine.models.geometry import (
    Door,
    Point,
    Project,
    Room,
    RoomType,
    Window,
)
from lighting_engine.parser.pipeline import parse_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


def _square_room(name: str, side: float = 4.0, floor: int = 0) -> Room:
    s = side / 2
    return Room(
        id=name.lower().replace(" ", "-"),
        name=name,
        type=RoomType.bedroom,
        floor_level=floor,
        polygon=[
            Point(x=-s, y=-s),
            Point(x=s, y=-s),
            Point(x=s, y=s),
            Point(x=-s, y=s),
        ],
        ceiling_height_m=2.7,
    )


def test_axis_aligned_rectangle_walls_have_correct_compass_orientation():
    room = _square_room("Test", side=4.0)
    project = Project(id="p1", name="x", rooms=[room])
    digest = compute_digest(project)
    rd = digest.rooms[0]
    # Polygon ordered CCW with vertices at corners:
    # 0→1 bottom edge (y=-2)   → outward normal -Y → S
    # 1→2 right edge (x=+2)    → outward normal +X → E
    # 2→3 top edge (y=+2)      → outward normal +Y → N
    # 3→0 left edge (x=-2)     → outward normal -X → W
    by_index = {w.index: w.orientation for w in rd.walls}
    assert by_index[0] == WallOrientation.S
    assert by_index[1] == WallOrientation.E
    assert by_index[2] == WallOrientation.N
    assert by_index[3] == WallOrientation.W


def test_window_position_attached_to_named_wall():
    room = _square_room("Bedroom", side=4.0)
    # Add a window on the top wall (wall_index=2), centred (along_wall=0.5)
    room.windows.append(Window(
        id="w1", wall_index=2, along_wall=0.5,
        width_m=1.5, height_m=1.5, sill_height_m=0.9,
    ))
    project = Project(id="p1", name="x", rooms=[room])
    digest = compute_digest(project)
    rd = digest.rooms[0]
    win = next(o for o in rd.openings if o.kind == "window")
    assert win.wall_index == 2
    assert rd.walls[win.wall_index].orientation == WallOrientation.N


def test_north_orientation_deg_rotates_compass():
    # If north_orientation_deg=90, what was East should become North
    room = _square_room("Rotated", side=4.0)
    project = Project(
        id="p1", name="x", north_orientation_deg=90, rooms=[room],
    )
    digest = compute_digest(project)
    by_index = {w.index: w.orientation for w in digest.rooms[0].walls}
    # The +X-facing wall (index 1) was East with north=0; rotate the compass 90° CW
    # → that wall is now on the North side
    assert by_index[1] == WallOrientation.N


def test_two_rooms_with_close_door_points_form_an_adjacency():
    room_a = _square_room("A", side=4.0)
    room_b = _square_room("B", side=4.0)
    # Shift B to the right so its left wall aligns with A's right wall at x=2
    room_b = room_b.model_copy(update={
        "polygon": [Point(x=p.x + 4.0, y=p.y) for p in room_b.polygon]
    })
    # Door on A's right wall (index 1), midway (along_wall=0.5)
    # That puts the door point at (2, 0)
    room_a.doors.append(Door(
        id="d1", wall_index=1, along_wall=0.5, width_m=0.9,
    ))
    # Door on B's left wall (index 3), midway → point also at (2, 0)
    room_b.doors.append(Door(
        id="d2", wall_index=3, along_wall=0.5, width_m=0.9,
    ))
    project = Project(id="p1", name="x", rooms=[room_a, room_b])
    digest = compute_digest(project)
    assert len(digest.adjacencies) == 1
    a = digest.adjacencies[0]
    assert {a.room_a_id, a.room_b_id} == {room_a.id, room_b.id}
    assert a.via == "door"


def test_summary_text_includes_dimensions_and_counts():
    room = _square_room("Master Bedroom", side=4.0)
    room.doors.append(Door(id="d1", wall_index=0, along_wall=0.5, width_m=0.9))
    project = Project(id="p1", name="x", rooms=[room])
    digest = compute_digest(project)
    summary = digest.rooms[0].summary
    assert "Master Bedroom" in summary
    assert "16.0 sqm" in summary or "16 sqm" in summary or "4.0m × 4.0m" in summary
    assert "1 door" in summary


def test_compute_digest_on_real_delhi_file():
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf", project_name="Mohak",
    )
    digest = compute_digest(project)
    # Every room from the project lands in the digest
    assert len(digest.rooms) == len(project.rooms)
    # Each room digest has walls with valid orientations
    for rd in digest.rooms:
        assert len(rd.walls) >= 3
        for w in rd.walls:
            assert isinstance(w.orientation, WallOrientation)
        assert rd.summary  # non-empty text summary
    # At least some openings landed on walls
    total_openings = sum(len(rd.openings) for rd in digest.rooms)
    assert total_openings >= 1, "real Delhi file should have at least some openings positioned"
