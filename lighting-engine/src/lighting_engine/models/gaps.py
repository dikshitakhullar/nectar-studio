"""Structured 'what we know / don't know' report from the parser.

The brief UI consumes this to ask the designer only the questions needed."""

from enum import StrEnum

from pydantic import BaseModel


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class MissingItem(BaseModel):
    category: str        # "ceiling_heights" | "north_arrow" | "windows" | "doors" | ...
    description: str
    severity: Severity = Severity.medium


class ExtractionSummary(BaseModel):
    rooms_found: int = 0
    walls_found: int = 0
    windows_found: int = 0
    doors_found: int = 0
    furniture_found: int = 0
    fixtures_found: int = 0
    height_labels_found: int = 0
    north_arrow_found: bool = False


class GapsReport(BaseModel):
    extraction: ExtractionSummary
    missing: list[MissingItem] = []

    def has_missing(self, category: str) -> bool:
        return any(m.category == category for m in self.missing)
