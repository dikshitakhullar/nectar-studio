"""Tests for the room PNG renderer.

We don't snapshot the bytes — matplotlib output isn't deterministic enough.
We verify the renderer produces valid PNG bytes of the expected size and
handles edge cases without raising.
"""

import io

from PIL import Image

from lighting_engine.design.room_render import render_room_for_vision
from lighting_engine.models.geometry import (
    Door,
    DoorSwing,
    Furniture,
    Point,
    Project,
    Room,
    Window,
)


def _rect_room(
    rid: str, name: str, x0: float, y0: float, x1: float, y1: float,
) -> Room:
    return Room(
        id=rid, name=name, type="bedroom", floor_level=0,
        polygon=[
            Point(x=x0, y=y0), Point(x=x1, y=y0),
            Point(x=x1, y=y1), Point(x=x0, y=y1),
        ],
        ceiling_height_m=2.7,
    )


def test_renders_valid_png_at_expected_size():
    project = Project(
        id="p", name="x", rooms=[_rect_room("r1", "BEDROOM-2", 0, 0, 5, 4)],
    )
    png = render_room_for_vision(project=project, room_id="r1")
    assert png.startswith(b"\x89PNG")
    img = Image.open(io.BytesIO(png))
    # 800x800 nominal; tight bbox crops to data extent. Just ensure the
    # image is large enough for Claude vision to read (>=500px each side).
    assert img.width >= 500
    assert img.height >= 500


def test_handles_room_with_doors_windows_and_furniture():
    room = _rect_room("r1", "BEDROOM-2", 0, 0, 5, 4)
    room = room.model_copy(update={
        "doors": [Door(
            id="d1", position=Point(x=2.5, y=0),
            wall_index=0, along_wall=0.5,
            width_m=0.9, swing=DoorSwing.in_,
        )],
        "windows": [Window(
            id="w1", position=Point(x=5, y=2),
            wall_index=1, along_wall=0.5,
            width_m=1.2, height_m=1.2, sill_height_m=0.9,
        )],
        "furniture": [Furniture(
            id="f1", type="BED", raw_label="BED-DOUBLE",
            position=Point(x=2.5, y=2),
            footprint=[
                Point(x=1.5, y=1), Point(x=3.5, y=1),
                Point(x=3.5, y=3), Point(x=1.5, y=3),
            ],
        )],
    })
    project = Project(id="p", name="x", rooms=[room])
    png = render_room_for_vision(project=project, room_id="r1")
    assert png.startswith(b"\x89PNG")


def test_handles_missing_room_gracefully():
    project = Project(id="p", name="x", rooms=[])
    png = render_room_for_vision(project=project, room_id="not-here")
    assert png.startswith(b"\x89PNG")  # placeholder still renders


def test_renders_with_multiple_neighbors():
    rooms = [
        _rect_room("r1", "BEDROOM-2", 0, 0, 5, 4),
        _rect_room("r2", "BATHROOM", 5, 0, 7, 3),
        _rect_room("r3", "PASSAGE", 0, 4, 5, 5),
    ]
    project = Project(id="p", name="x", rooms=rooms)
    png = render_room_for_vision(project=project, room_id="r1")
    assert png.startswith(b"\x89PNG")
