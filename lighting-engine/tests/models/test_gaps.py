from lighting_engine.models.gaps import (
    ExtractionSummary,
    GapsReport,
    MissingItem,
    Severity,
)


def test_extraction_summary_counts_default_to_zero():
    s = ExtractionSummary()
    assert s.rooms_found == 0
    assert s.walls_found == 0
    assert s.height_labels_found == 0


def test_gaps_report_groups_missing_by_category():
    rep = GapsReport(
        extraction=ExtractionSummary(rooms_found=8, walls_found=2100),
        missing=[
            MissingItem(
                category="ceiling_heights",
                description="No ceiling heights found",
                severity=Severity.high,
            ),
            MissingItem(
                category="north_arrow",
                description="No north arrow detected",
                severity=Severity.medium,
            ),
        ],
    )
    assert rep.has_missing("ceiling_heights")
    assert not rep.has_missing("furniture")


def test_severity_enum_values():
    assert {s.value for s in Severity} == {"low", "medium", "high"}
