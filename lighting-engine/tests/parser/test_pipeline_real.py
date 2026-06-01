from pathlib import Path

from lighting_engine.parser.pipeline import parse_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"

# Rooms we expect the architect's labels to yield. Minimum-success set.
_EXPECTED_ROOMS = {
    "MASTER BEDROOM", "STUDY ROOM", "BEDROOM - 1", "BEDROOM - 2",
    "MASTER TOILET", "TOILET - 1", "TOILET - 2", "LOBBY",
    "DRESS - 1", "MASTER DRESS",
}


def test_parse_real_architectural_dxf_end_to_end():
    project, report = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="Mohak Residence",
        location="delhi",
    )
    names = {r.name for r in project.rooms}
    # Checkpoint A acceptance: ≥80% of the expected set recalled
    found = _EXPECTED_ROOMS & names
    recall = len(found) / len(_EXPECTED_ROOMS)
    assert recall >= 0.8, f"recall {recall:.0%}; missing {_EXPECTED_ROOMS - names}"
    # Every room has a non-empty polygon and a positive area
    for room in project.rooms:
        assert len(room.polygon) >= 3
        assert room.area_sqm > 0
    # Gaps report reflects parser state
    assert report.extraction.rooms_found == len(project.rooms)
    # Real arch file has no ceiling-height labels, so this gap should be flagged
    assert report.has_missing("ceiling_heights")


def test_parse_dwg_round_trip_via_libredwg():
    # Same architectural plan but via the .dwg source — should produce a similar room set
    project_dxf, _ = parse_file(FIXTURES / "real_base_architectural.dxf", project_name="x")
    project_dwg, _ = parse_file(FIXTURES / "real_base_architectural.dwg", project_name="x")
    names_dxf = {r.name for r in project_dxf.rooms}
    names_dwg = {r.name for r in project_dwg.rooms}
    # Allow minor differences from conversion noise; require ≥80% overlap
    overlap = len(names_dxf & names_dwg) / max(len(names_dxf), 1)
    assert overlap >= 0.8, f"DXF↔DWG overlap {overlap:.0%}"
