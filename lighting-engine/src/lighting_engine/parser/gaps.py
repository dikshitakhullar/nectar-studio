"""Build a GapsReport from parsing state.

The brief UI uses the report to ask the designer only the questions needed."""

from lighting_engine.models.gaps import (
    ExtractionSummary,
    GapsReport,
    MissingItem,
    Severity,
)
from lighting_engine.models.geometry import Room
from lighting_engine.parser.entities import AttachSummary


def build_gaps_report(
    rooms: list[Room],
    attach: AttachSummary,
    *,
    north_arrow_found: bool,
    height_labels_found: int,
) -> GapsReport:
    extraction = ExtractionSummary(
        rooms_found=len(rooms),
        walls_found=attach.walls_seen,
        windows_found=attach.windows_attached,
        doors_found=attach.doors_attached,
        furniture_found=attach.furniture_attached,
        fixtures_found=attach.fixtures_attached,
        height_labels_found=height_labels_found,
        north_arrow_found=north_arrow_found,
    )
    missing: list[MissingItem] = []
    if height_labels_found < len(rooms):
        missing.append(MissingItem(
            category="ceiling_heights",
            description=(
                f"No ceiling heights found for {len(rooms) - height_labels_found} room(s) — "
                "designer must supply via brief"
            ),
            severity=Severity.high,
        ))
    if not north_arrow_found:
        missing.append(MissingItem(
            category="north_arrow",
            description="No north arrow detected — designer must confirm orientation",
            severity=Severity.medium,
        ))
    if attach.windows_attached == 0 and rooms:
        missing.append(MissingItem(
            category="windows",
            description=(
                "No windows attached — daylight pass will be skipped until designer adds them"
            ),
            severity=Severity.medium,
        ))
    if attach.doors_attached == 0 and rooms:
        missing.append(MissingItem(
            category="doors",
            description="No doors attached — switch placement guidance will be limited",
            severity=Severity.low,
        ))
    return GapsReport(extraction=extraction, missing=missing)
