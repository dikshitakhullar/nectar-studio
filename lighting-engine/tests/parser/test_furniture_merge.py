"""Tests for ``parser.furniture_merge``.

The synthetic tests cover:
  * zero-offset alignment (the common case) — furniture INSERT placed inside
    a known room polygon attaches to that room.
  * brute-force offset recovery — the same INSERT shifted by a metres-scale
    translation is still found and attached.
  * appliance-label detection — a TEXT entity matching an appliance word is
    treated as a furniture marker.
  * out-of-region dropping — entities outside every room are reported but
    not attached.

The real-file test ("BASE FILE.dxf" + "FURNITURE DIMNS GROUND & FIRST.dwg")
runs when the user's Delhi fixtures are present in ~/Downloads. Asserts that
≥10 furniture items attach across the rooms and prints the report so we can
eyeball the offset/inlier ratio.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import ezdxf
import pytest

from lighting_engine.models.geometry import Point, Project, Room, RoomType
from lighting_engine.parser.furniture_merge import (
    MergeReport,
    merge_furniture_from_file,
)
from lighting_engine.parser.pipeline import parse_file

INCH_TO_M = 0.0254
M_TO_INCH = 1.0 / INCH_TO_M


def _square_room(name: str, cx: float, cy: float, side: float = 4.0) -> Room:
    s = side / 2.0
    return Room(
        id=name.lower(),
        name=name,
        type=RoomType.living,
        polygon=[
            Point(x=cx - s, y=cy - s),
            Point(x=cx + s, y=cy - s),
            Point(x=cx + s, y=cy + s),
            Point(x=cx - s, y=cy + s),
        ],
        ceiling_height_m=2.7,
    )


def _project_with_one_room(room: Room) -> Project:
    return Project(
        id=str(uuid.uuid4()),
        name="Synthetic",
        location="delhi",
        floor_level=0,
        rooms=[room],
    )


def _write_furniture_dxf(
    path: Path,
    *,
    insert_positions_in: list[tuple[float, float]] | None = None,
    text_entries: list[tuple[str, tuple[float, float]]] | None = None,
    boundary_segments_in: list[
        tuple[tuple[float, float], tuple[float, float]]
    ] | None = None,
) -> None:
    """Write a synthetic furniture DXF.

    All coordinates supplied in DXF inches (since INSUNITS=1). The optional
    boundary segments are placed on a ``WALL`` layer so ``find_plan_region``
    has something to cluster on; the optional INSERTs go on a ``FURNITURE``
    layer; TEXTs go on a free-form ``TEXT`` layer.
    """
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1
    if "WALL" not in doc.layers:
        doc.layers.add("WALL")
    if "FURNITURE" not in doc.layers:
        doc.layers.add("FURNITURE")
    if "TEXT" not in doc.layers:
        doc.layers.add("TEXT")
    if insert_positions_in and "SOFA" not in doc.blocks:
        blk = doc.blocks.new(name="SOFA")
        # Minimal block content — a single line so ezdxf is happy.
        blk.add_line((0, 0), (1, 0))
    msp = doc.modelspace()

    # Default boundary: a 200x200 inch square so find_plan_region picks the
    # region around (0, 200). Easier than asking each test to supply one.
    if boundary_segments_in is None:
        boundary_segments_in = [
            ((0.0, 0.0), (200.0, 0.0)),
            ((200.0, 0.0), (200.0, 200.0)),
            ((200.0, 200.0), (0.0, 200.0)),
            ((0.0, 200.0), (0.0, 0.0)),
        ]
    for a, b in boundary_segments_in:
        msp.add_line(a, b, dxfattribs={"layer": "WALL"})

    for x, y in insert_positions_in or []:
        msp.add_blockref("SOFA", (x, y), dxfattribs={"layer": "FURNITURE"})

    for text, (x, y) in text_entries or []:
        msp.add_text(
            text,
            dxfattribs={"layer": "TEXT", "insert": (x, y)},
        )

    doc.saveas(str(path))


# ---------------------------------------------------------------------------
# Synthetic tests
# ---------------------------------------------------------------------------


def test_merge_zero_offset_attaches_furniture_to_room(tmp_path: Path) -> None:
    """Furniture INSERT and architectural room share a frame → attach."""
    # Room polygon spans (0, 0) → (5, 4) meters. Place a furniture INSERT
    # at (2.5, 2.0) meters → in DXF inches that's (~98.4, ~78.7).
    room = Room(
        id="living",
        name="LIVING",
        type=RoomType.living,
        polygon=[
            Point(x=0.0, y=0.0),
            Point(x=5.0, y=0.0),
            Point(x=5.0, y=4.0),
            Point(x=0.0, y=4.0),
        ],
        ceiling_height_m=2.7,
    )
    project = _project_with_one_room(room)

    insert_x_in = 2.5 * M_TO_INCH  # ≈ 98.43 inch
    insert_y_in = 2.0 * M_TO_INCH  # ≈ 78.74 inch
    # Boundary square 0..(5m in inches) so the region origin lines up with
    # the architectural room's (0,0).
    far = 5.0 * M_TO_INCH
    fpath = tmp_path / "furniture.dxf"
    _write_furniture_dxf(
        fpath,
        insert_positions_in=[(insert_x_in, insert_y_in)],
        boundary_segments_in=[
            ((0.0, 0.0), (far, 0.0)),
            ((far, 0.0), (far, far)),
            ((far, far), (0.0, far)),
            ((0.0, far), (0.0, 0.0)),
        ],
    )

    merged, report = merge_furniture_from_file(project, fpath)

    assert isinstance(report, MergeReport)
    assert report.furniture_seen == 1
    assert report.furniture_attached == 1
    assert report.dropped_outside_rooms == 0
    assert report.offset_applied_m == (0.0, 0.0)
    assert report.inlier_ratio == 1.0
    assert len(merged.rooms[0].furniture) == 1
    f = merged.rooms[0].furniture[0]
    assert f.raw_label == "SOFA"
    # Position is in the architectural local-meter frame.
    assert abs(f.position.x - 2.5) < 0.01
    assert abs(f.position.y - 2.0) < 0.01


def test_merge_does_not_mutate_input_project(tmp_path: Path) -> None:
    """``merge_furniture_from_file`` returns a copy — the input is unchanged."""
    room = _square_room("Living", cx=2.5, cy=2.0)
    project = _project_with_one_room(room)
    original_count = len(project.rooms[0].furniture)

    far = 5.0 * M_TO_INCH
    fpath = tmp_path / "furniture.dxf"
    _write_furniture_dxf(
        fpath,
        insert_positions_in=[(2.5 * M_TO_INCH, 2.0 * M_TO_INCH)],
        boundary_segments_in=[
            ((0.0, 0.0), (far, 0.0)),
            ((far, 0.0), (far, far)),
            ((far, far), (0.0, far)),
            ((0.0, far), (0.0, 0.0)),
        ],
    )

    _merged, _report = merge_furniture_from_file(project, fpath)
    assert len(project.rooms[0].furniture) == original_count


def test_merge_appliance_text_label_attached(tmp_path: Path) -> None:
    """A TEXT entity matching an appliance word is treated as furniture."""
    room = Room(
        id="kitchen",
        name="KITCHEN",
        type=RoomType.kitchen,
        polygon=[
            Point(x=0.0, y=0.0),
            Point(x=4.0, y=0.0),
            Point(x=4.0, y=3.0),
            Point(x=0.0, y=3.0),
        ],
        ceiling_height_m=2.7,
    )
    project = _project_with_one_room(room)

    far = 4.0 * M_TO_INCH
    fpath = tmp_path / "furniture.dxf"
    _write_furniture_dxf(
        fpath,
        text_entries=[("FRIDGE", (1.0 * M_TO_INCH, 1.0 * M_TO_INCH))],
        boundary_segments_in=[
            ((0.0, 0.0), (far, 0.0)),
            ((far, 0.0), (far, far)),
            ((far, far), (0.0, far)),
            ((0.0, far), (0.0, 0.0)),
        ],
    )

    merged, report = merge_furniture_from_file(project, fpath)

    assert report.furniture_seen == 1
    assert report.furniture_attached == 1
    assert len(merged.rooms[0].furniture) == 1
    assert merged.rooms[0].furniture[0].raw_label == "FRIDGE"


def test_merge_drops_entity_outside_every_room(tmp_path: Path) -> None:
    """When most furniture aligns to a room, the stray one outside is dropped.

    The hint+brute-force search aligns the bulk of the furniture to the
    rooms; entities that don't fall inside any room after registration are
    reported as ``dropped_outside_rooms`` (and not attached).
    """
    room = Room(
        id="bedroom",
        name="BEDROOM",
        type=RoomType.bedroom,
        polygon=[
            Point(x=0.0, y=0.0),
            Point(x=3.0, y=0.0),
            Point(x=3.0, y=3.0),
            Point(x=0.0, y=3.0),
        ],
        ceiling_height_m=2.7,
    )
    project = _project_with_one_room(room)

    # Three INSERTs inside the room polygon + one well outside it. The
    # inside ones drive the alignment hint; the outside one survives
    # alignment without landing in any room.
    inside = [
        (0.5 * M_TO_INCH, 0.5 * M_TO_INCH),
        (1.5 * M_TO_INCH, 1.5 * M_TO_INCH),
        (2.5 * M_TO_INCH, 2.5 * M_TO_INCH),
    ]
    outside = (15.0 * M_TO_INCH, 15.0 * M_TO_INCH)
    far = 20.0 * M_TO_INCH
    fpath = tmp_path / "furniture.dxf"
    _write_furniture_dxf(
        fpath,
        insert_positions_in=[*inside, outside],
        boundary_segments_in=[
            ((0.0, 0.0), (far, 0.0)),
            ((far, 0.0), (far, far)),
            ((far, far), (0.0, far)),
            ((0.0, far), (0.0, 0.0)),
        ],
    )

    merged, report = merge_furniture_from_file(project, fpath)
    assert report.furniture_seen == 4
    # The three inside-the-room INSERTs attach; the one outside is dropped.
    assert report.furniture_attached == 3
    assert report.dropped_outside_rooms == 1
    assert len(merged.rooms[0].furniture) == 3


def test_merge_recovers_known_offset_via_brute_force(tmp_path: Path) -> None:
    """A furniture file shifted by ~2m from the architectural frame still
    attaches its INSERTs to the right rooms.

    Build an architectural project with one room at (0, 0)-(4, 4) m, then
    write a furniture file whose INSERTs sit at the same shape but shifted
    by (+2 m, +2 m) in the file's *own* coordinate frame. After the merge,
    those inserts must end up in the room — meaning the offset detection
    found and applied roughly (-2, -2). This exercises the brute-force
    grid: zero-offset would put every insert outside the room.
    """
    room = Room(
        id="study",
        name="STUDY",
        type=RoomType.study,
        polygon=[
            Point(x=0.0, y=0.0),
            Point(x=4.0, y=0.0),
            Point(x=4.0, y=4.0),
            Point(x=0.0, y=4.0),
        ],
        ceiling_height_m=2.7,
    )
    project = _project_with_one_room(room)

    # Three INSERTs inside what *should* be the room — but shifted by
    # (+2 m, +2 m) in the furniture file's frame. So in raw DXF inches:
    # furniture positions are at (2..5, 2..5) m → (78.7..196.9 in).
    shift_m = 2.0
    inserts_in = [
        ((1.0 + shift_m) * M_TO_INCH, (1.0 + shift_m) * M_TO_INCH),
        ((2.0 + shift_m) * M_TO_INCH, (2.0 + shift_m) * M_TO_INCH),
        ((3.0 + shift_m) * M_TO_INCH, (3.0 + shift_m) * M_TO_INCH),
    ]
    # Boundary covers the shifted area so find_plan_region picks a
    # furniture-local frame whose origin is at the boundary bottom-left.
    far = (6.0 + shift_m) * M_TO_INCH
    fpath = tmp_path / "furniture_shifted.dxf"
    _write_furniture_dxf(
        fpath,
        insert_positions_in=inserts_in,
        boundary_segments_in=[
            ((shift_m * M_TO_INCH, shift_m * M_TO_INCH), (far, shift_m * M_TO_INCH)),
            ((far, shift_m * M_TO_INCH), (far, far)),
            ((far, far), (shift_m * M_TO_INCH, far)),
            ((shift_m * M_TO_INCH, far), (shift_m * M_TO_INCH, shift_m * M_TO_INCH)),
        ],
    )

    merged, report = merge_furniture_from_file(project, fpath)

    assert report.furniture_seen == 3
    assert report.furniture_attached == 3, (
        f"expected brute-force search to align furniture; report: {report}"
    )
    # Inlier ratio after registration should be 1.0 — all 3 attached.
    assert report.inlier_ratio == 1.0


def test_merge_handles_missing_or_empty_file(tmp_path: Path) -> None:
    """An empty furniture DXF (no entities) returns a zero-report and doesn't crash."""
    room = _square_room("Living", cx=2.5, cy=2.0)
    project = _project_with_one_room(room)

    fpath = tmp_path / "empty.dxf"
    # Write a valid DXF with no modelspace content (just a layer).
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1
    doc.saveas(str(fpath))

    merged, report = merge_furniture_from_file(project, fpath)
    assert report.furniture_seen == 0
    assert report.furniture_attached == 0
    assert report.inlier_ratio == 0.0
    assert len(merged.rooms[0].furniture) == 0


# ---------------------------------------------------------------------------
# Real-file integration (skipped when fixtures aren't present)
# ---------------------------------------------------------------------------


_BASE_DXF = Path.home() / "Downloads" / "BASE FILE.dxf"
_FURNITURE_DWG = Path.home() / "Downloads" / "FURNITURE DIMNS GROUND & FIRST.dwg"


@pytest.mark.skipif(
    not _BASE_DXF.exists() or not _FURNITURE_DWG.exists(),
    reason="Delhi BASE FILE.dxf + FURNITURE DWG not present in ~/Downloads",
)
def test_merge_real_delhi_furniture_attaches_to_rooms() -> None:
    """End-to-end on real Delhi fixtures: ≥10 furniture items attach."""
    project, _gaps = parse_file(_BASE_DXF, project_name="Delhi")
    # Make sure the parse actually produced rooms — if it didn't, this test
    # would pass vacuously since there's nothing to attach to.
    assert len(project.rooms) > 0

    # Copy the furniture file into a tmp dir so the test doesn't accidentally
    # write artefacts next to it.
    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "furniture.dwg"
        local.write_bytes(_FURNITURE_DWG.read_bytes())
        merged, report = merge_furniture_from_file(project, local)

    print("\nMergeReport (real Delhi fixtures):", report)
    # Sanity: at least one room ended up with some furniture.
    total_attached = sum(len(r.furniture) for r in merged.rooms)
    print(f"  total furniture attached across rooms: {total_attached}")
    print(f"  rooms with ≥1 furniture: "
          f"{sum(1 for r in merged.rooms if r.furniture)}")
    assert total_attached >= 10, (
        f"expected ≥10 furniture items attached; got {total_attached}. "
        f"Report: {report}"
    )
