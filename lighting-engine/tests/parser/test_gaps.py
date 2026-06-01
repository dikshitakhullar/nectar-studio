from lighting_engine.models.gaps import Severity
from lighting_engine.models.geometry import Point, Room, RoomType
from lighting_engine.parser.entities import AttachSummary
from lighting_engine.parser.gaps import build_gaps_report


def _room(name: str) -> Room:
    return Room(
        id=name.lower(),
        name=name,
        type=RoomType.bedroom,
        polygon=[Point(x=0, y=0), Point(x=4, y=0), Point(x=4, y=3), Point(x=0, y=3)],
        ceiling_height_m=2.7,
    )


def test_missing_ceiling_heights_is_high_severity():
    rooms = [_room("R1"), _room("R2")]
    summary = AttachSummary(
        walls_seen=100, doors_attached=2, windows_attached=1, fixtures_attached=4
    )
    report = build_gaps_report(rooms, summary, north_arrow_found=True, height_labels_found=0)
    assert report.has_missing("ceiling_heights")
    missing_item = next(m for m in report.missing if m.category == "ceiling_heights")
    assert missing_item.severity == Severity.high


def test_missing_north_arrow_recorded():
    summary = AttachSummary(walls_seen=10)
    report = build_gaps_report(
        [_room("R1")], summary, north_arrow_found=False, height_labels_found=1
    )
    assert report.has_missing("north_arrow")


def test_no_missing_items_when_everything_complete():
    summary = AttachSummary(
        walls_seen=10, doors_attached=2, windows_attached=2,
        furniture_attached=5, fixtures_attached=4,
    )
    report = build_gaps_report(
        [_room("R1")], summary, north_arrow_found=True, height_labels_found=1,
    )
    assert report.missing == []


def test_no_windows_attached_warns():
    summary = AttachSummary(walls_seen=10, doors_attached=2, windows_attached=0)
    report = build_gaps_report(
        [_room("R1")], summary, north_arrow_found=True, height_labels_found=1
    )
    assert report.has_missing("windows")
