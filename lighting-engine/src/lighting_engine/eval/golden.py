"""Golden-set spec: the hand-edited source of truth for what the parser SHOULD produce.

A golden YAML lives per fixture (`tests/eval/golden/<file>.yaml`). It lists the
expected rooms (name + type + floor) plus structural invariants (no overlaps,
minimum staircase count). The scorer compares parser output to this spec.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from lighting_engine.models.geometry import RoomType


class GoldenRoom(BaseModel):
    name: str                      # exact match against Room.name
    type: RoomType                 # exact match against Room.type
    floor_level: int = 0
    optional: bool = False         # if True, absence is OK (e.g. SHAFT count varies)


class GoldenSpec(BaseModel):
    file: str                      # filename of the fixture (DXF or DWG)
    expected_rooms: list[GoldenRoom]
    expected_staircases_min: int = Field(default=0, ge=0)
    require_no_overlaps: bool = True


def load_golden(path: Path | str) -> GoldenSpec:
    """Load a golden YAML file into a typed GoldenSpec."""
    raw = yaml.safe_load(Path(path).read_text())
    return GoldenSpec.model_validate(raw)
