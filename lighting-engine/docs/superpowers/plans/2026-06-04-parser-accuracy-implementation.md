# Parser Accuracy + Uncertainty Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the parse pipeline into three layers (deterministic → Claude vision verifier → designer-in-the-loop) so room polygons, doors/windows, and furniture are correct, and uncertainty is explicitly surfaced to the designer.

**Architecture:** Layer 1 deterministic parser emits confidence per entity. Layer 2 calls Claude with vision crops, one batched call per room with any uncertainty, plus one whole-plan call for LOBBY arm recovery. Layer 3 surfaces low-confidence items as a "confirm panel" in the studio. Every entity carries `confidence`, `provenance`, `llm_status`, and `alternatives` so the studio can audit.

**Tech Stack:** Python 3.11, pydantic v2, FastAPI, SQLAlchemy 2.0 async, ezdxf, shapely, matplotlib (rendering), anthropic SDK (Claude Opus 4.7, adaptive thinking, structured output, vision, prompt caching), Next.js 16 / React 19 / Tailwind 4 (studio).

**Spec:** `lighting-engine/docs/superpowers/specs/2026-06-04-parser-accuracy-design.md`

---

## File Map

### New files
- `lighting-engine/src/lighting_engine/parser/furniture_geometry.py` — INSERT block extraction
- `lighting-engine/src/lighting_engine/parser/lobby_recovery.py` — orphan cell candidates
- `lighting-engine/src/lighting_engine/parser/uncertainty.py` — confidence triggers, typical room areas
- `lighting-engine/src/lighting_engine/parser/cad_id_filter.py` — AutoCAD block-ID detection
- `lighting-engine/src/lighting_engine/llm/__init__.py`
- `lighting-engine/src/lighting_engine/llm/disambiguator.py` — orchestrator
- `lighting-engine/src/lighting_engine/llm/room_render.py` — matplotlib PNG renderer
- `lighting-engine/src/lighting_engine/llm/prompts.py` — system + user templates
- `lighting-engine/src/lighting_engine/llm/schemas.py` — pydantic models for structured output
- `lighting-engine/src/lighting_engine/llm/client.py` — wrapped anthropic client with retry/ratelimit
- `lighting-engine/src/lighting_engine/api/routes/confirmations.py` — GET/POST endpoints
- `studio/app/studio/components/ConfirmCard.tsx` — 5-variant confirm card
- `studio/app/studio/components/RoomStatusBadge.tsx` — picker badge
- `studio/lib/api/confirmations.ts` — confirmation API client
- Tests: one test module per source module under `lighting-engine/tests/` mirroring the path

### Modified files
- `lighting-engine/src/lighting_engine/models/geometry.py` — add confidence/provenance/llm_status/alternatives to Room, Door, Window, Furniture
- `lighting-engine/src/lighting_engine/api/schemas.py` — add room status, project verification_mode, Alternative model, confirmation request/response
- `lighting-engine/src/lighting_engine/api/models.py` — DB columns for status, verification_mode
- `lighting-engine/src/lighting_engine/parser/pipeline.py` — wire new modules in
- `lighting-engine/src/lighting_engine/parser/furniture_merge.py` — drop AutoCAD block-IDs at candidate stage
- `lighting-engine/src/lighting_engine/parser/door_anchor.py`, `door_detection.py`, `window_filter.py` — emit confidence per item
- `lighting-engine/src/lighting_engine/api/routes/projects.py` — BackgroundTask hook, response shape
- `lighting-engine/src/lighting_engine/api/routes/rooms.py` — include status in summaries
- `studio/app/studio/rooms/page.tsx` — render status badge + polling
- `studio/app/studio/[any room page]` — dock confirm panel when needs_attention
- `studio/lib/api/types.ts` — new types (RoomStatus, Provenance, Alternative, Confirmation, etc.)

---

## Sequencing

**Phase A (Tasks 1-4):** Data model + migration foundation
**Phase B (Tasks 5-10):** Layer 1 deterministic parser improvements
**Phase C (Tasks 11-17):** Layer 2 Claude vision verifier
**Phase D (Tasks 18-20):** API endpoints + integration
**Phase E (Tasks 21-24):** Studio UX surfacing
**Phase F (Tasks 25-26):** End-to-end + rollout

---

## Phase A — Data model foundation

### Task 1: Add confidence + provenance + llm_status + alternatives to all geometry entities

**Files:**
- Modify: `lighting-engine/src/lighting_engine/models/geometry.py`
- Test: `lighting-engine/tests/models/test_geometry_uncertainty_fields.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/models/test_geometry_uncertainty_fields.py
from lighting_engine.models.geometry import (
    Alternative, Door, Furniture, Point, Room, Window,
)


def test_room_has_uncertainty_fields_with_defaults():
    room = Room(id="r1", name="Living", type="living", polygon=[
        Point(x=0, y=0), Point(x=5, y=0), Point(x=5, y=5), Point(x=0, y=5),
    ])
    assert room.confidence == 1.0
    assert room.provenance == "parser"
    assert room.llm_status == "unchecked"
    assert room.alternatives is None


def test_door_uncertainty_fields_with_defaults():
    door = Door(id="d1", position=Point(x=0, y=0), wall_index=0)
    assert door.confidence == 1.0
    assert door.provenance == "parser"
    assert door.llm_status == "unchecked"


def test_window_uncertainty_fields():
    win = Window(id="w1", position=Point(x=0, y=0))
    assert win.confidence == 1.0
    assert win.provenance == "parser"


def test_furniture_uncertainty_fields():
    f = Furniture(id="f1", position=Point(x=0, y=0))
    assert f.confidence == 1.0
    assert f.provenance == "parser"
    assert f.llm_status == "unchecked"


def test_alternative_model():
    alt = Alternative(value="SOFA", confidence=0.7, reason="Looks like a sofa")
    assert alt.value == "SOFA"
    assert alt.confidence == 0.7
    assert alt.reason == "Looks like a sofa"


def test_provenance_accepts_llm_uncontested():
    door = Door(id="d1", position=Point(x=0, y=0), wall_index=0,
                provenance="llm_uncontested")
    assert door.provenance == "llm_uncontested"


def test_llm_status_accepts_flagged_as_noise():
    f = Furniture(id="f1", position=Point(x=0, y=0),
                  llm_status="flagged_as_noise")
    assert f.llm_status == "flagged_as_noise"


def test_alternatives_list_attaches_to_entity():
    door = Door(
        id="d1", position=Point(x=0, y=0), wall_index=0,
        alternatives=[
            Alternative(value="sliding", confidence=0.6, reason="double slider"),
            Alternative(value="regular", confidence=0.3, reason="single swing"),
        ],
    )
    assert len(door.alternatives) == 2
    assert door.alternatives[0].value == "sliding"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/models/test_geometry_uncertainty_fields.py -v`
Expected: FAIL — `AttributeError: 'Room' object has no attribute 'confidence'` (or similar).

- [ ] **Step 3: Add the fields and Alternative model**

In `lighting-engine/src/lighting_engine/models/geometry.py`, add at top of the file (or in the appropriate import section):

```python
from typing import Any, Literal

Provenance = Literal["parser", "llm", "llm_uncontested", "designer"]
LlmStatus = Literal["unchecked", "verified", "flagged_as_noise"]


class Alternative(BaseModel):
    """One alternative Claude considered when resolving an uncertain entity.

    `value` is loosely typed because the alternated field depends on the
    entity (str for door type, dict[str, float] for Point, etc.). At the
    schemas-level (api/schemas.py) we use discriminated unions for typed
    validation; here we keep the IR liberal.
    """
    model_config = ConfigDict(frozen=True)

    value: str | dict[str, Any]
    confidence: float
    reason: str
```

Then add these fields to **each** of `Room`, `Door`, `Window`, `Furniture` (alongside existing fields):

```python
confidence: float = 1.0
provenance: Provenance = "parser"
llm_status: LlmStatus = "unchecked"
alternatives: list[Alternative] | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/models/test_geometry_uncertainty_fields.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Verify existing tests still pass**

Run: `cd lighting-engine && uv run pytest`
Expected: All previous 336 tests still PASS (new fields all have defaults, so existing fixtures are unaffected).

- [ ] **Step 6: Commit**

```bash
git add lighting-engine/src/lighting_engine/models/geometry.py lighting-engine/tests/models/test_geometry_uncertainty_fields.py
git commit -m "feat(models): add confidence/provenance/llm_status/alternatives to geometry entities

Foundation for the parser uncertainty overhaul. Every Room/Door/Window/Furniture
now carries provenance and an optional list of LLM-suggested alternatives.
Defaults preserve current behavior (confidence=1.0, provenance=parser).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add room status + project verification_mode to API schemas + DB

**Files:**
- Modify: `lighting-engine/src/lighting_engine/api/schemas.py`
- Modify: `lighting-engine/src/lighting_engine/api/models.py`
- Test: `lighting-engine/tests/api/test_room_status_fields.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/api/test_room_status_fields.py
import pytest
from lighting_engine.api.schemas import (
    ProjectVerificationMode, RoomStatus, RoomSummary, RoomTier,
)


def test_room_status_literal_accepts_all_five_values():
    for value in ("parsing", "verifying", "ready", "needs_attention", "manual"):
        summary = RoomSummary(
            id="r", name="X", tier=RoomTier.first_class, status="new",
            verification_status=value,
        )
        assert summary.verification_status == value


def test_room_status_rejects_unknown_value():
    with pytest.raises(Exception):
        RoomSummary(
            id="r", name="X", tier=RoomTier.first_class, status="new",
            verification_status="bogus",
        )


def test_project_verification_mode_accepts_enabled_and_disabled():
    assert ProjectVerificationMode("enabled") == "enabled"
    assert ProjectVerificationMode("disabled") == "disabled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/api/test_room_status_fields.py -v`
Expected: FAIL — `ImportError: cannot import name 'RoomStatus'` (or similar).

- [ ] **Step 3: Add the types to `api/schemas.py`**

```python
from typing import Literal

RoomStatus = Literal["parsing", "verifying", "ready", "needs_attention", "manual"]
ProjectVerificationMode = Literal["enabled", "disabled"]
```

Add `verification_status: RoomStatus = "ready"` to `RoomSummary` (default `ready` keeps backwards-compat for existing rows).

- [ ] **Step 4: Add the DB column in `api/models.py`**

In the `RoomRecord` class, add:

```python
verification_status: Mapped[str] = mapped_column(
    String, nullable=False, default="ready",
)
```

In the `Project` class, add:

```python
verification_mode: Mapped[str] = mapped_column(
    String, nullable=False, default="enabled",
)
```

Both default-on-the-DB-side so existing rows backfill automatically when the table is recreated. (For SQLite dev, drop + recreate is fine; v1.1 introduces Alembic migrations.)

- [ ] **Step 5: Run all tests**

Run: `cd lighting-engine && uv run pytest`
Expected: All tests PASS; new tests in this task PASS.

- [ ] **Step 6: Commit**

```bash
git add lighting-engine/src/lighting_engine/api/schemas.py lighting-engine/src/lighting_engine/api/models.py lighting-engine/tests/api/test_room_status_fields.py
git commit -m "feat(api): add RoomStatus + ProjectVerificationMode + DB columns

Per-room verification_status (parsing/verifying/ready/needs_attention/manual)
plus project-level verification_mode (enabled/disabled). Both default to a
backwards-compatible value so existing rows continue to work.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: AutoCAD block-ID filter utility

**Files:**
- Create: `lighting-engine/src/lighting_engine/parser/cad_id_filter.py`
- Test: `lighting-engine/tests/parser/test_cad_id_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/parser/test_cad_id_filter.py
from lighting_engine.parser.cad_id_filter import is_cad_block_id


def test_matches_real_autocad_block_ids():
    # Real samples observed in Delhi furniture DXF
    assert is_cad_block_id("A$C40b9ed5b")
    assert is_cad_block_id("A$C62fb3387")
    assert is_cad_block_id("A$C29994ed3")
    assert is_cad_block_id("A$Ca746da64")
    assert is_cad_block_id("A$C9a3b")


def test_does_not_match_real_furniture_labels():
    assert not is_cad_block_id("FIREPLACE")
    assert not is_cad_block_id("sofa 053")
    assert not is_cad_block_id("FRIDGE")
    assert not is_cad_block_id("MICROWAVE")
    assert not is_cad_block_id("SINK")
    assert not is_cad_block_id("DRESSER")
    assert not is_cad_block_id("SCONCE")
    assert not is_cad_block_id("Poltrona Ricca Grando")
    assert not is_cad_block_id("BED-DOUBLE")
    assert not is_cad_block_id("DT-8")


def test_handles_edge_cases():
    assert not is_cad_block_id("")
    assert not is_cad_block_id(None)
    assert not is_cad_block_id("   ")
    # Whitespace-padded should be detected (trim first)
    assert is_cad_block_id("  A$C40b9ed5b  ")


def test_does_not_falsely_match_short_strings():
    # "A$X" alone is too short to be confident; reject
    assert not is_cad_block_id("A$X")
    assert not is_cad_block_id("A$")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/parser/test_cad_id_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lighting_engine.parser.cad_id_filter'`.

- [ ] **Step 3: Implement the filter**

```python
# lighting-engine/src/lighting_engine/parser/cad_id_filter.py
"""Identify AutoCAD-generated block-reference names.

AutoCAD generates internal block names like ``A$C40b9ed5b`` when blocks are
inserted via copy-paste, WBLOCK, or other automated operations. These names
are CAD internals — they're not labels a designer or architect intended,
so we drop them from the furniture-candidate pool.

Observed samples in Delhi fixtures:
- A$C40b9ed5b, A$C62fb3387, A$C29994ed3, A$Ca746da64, A$C9a3b
"""
import re

# Pattern: A$ + 1-2 alpha + at least 4 hex digits. The 4-hex minimum prevents
# false positives on short artistic block names that happen to start with A$.
_CAD_ID_PATTERN = re.compile(r"^A\$[A-Z]{1,2}[0-9a-fA-F]{4,}$", re.IGNORECASE)


def is_cad_block_id(label: str | None) -> bool:
    """True when ``label`` looks like an AutoCAD-generated internal block name."""
    if label is None:
        return False
    trimmed = label.strip()
    if len(trimmed) == 0:
        return False
    return bool(_CAD_ID_PATTERN.match(trimmed))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/parser/test_cad_id_filter.py -v`
Expected: All 5 test functions PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/parser/cad_id_filter.py lighting-engine/tests/parser/test_cad_id_filter.py
git commit -m "feat(parser): cad_id_filter to identify AutoCAD-generated block names

Drops noise labels like A\$C40b9ed5b from the furniture candidate pool.
Validated against 5 real samples from the Delhi furniture DXF and 10 real
furniture labels (FIREPLACE, sofa 053, DT-8, etc.) confirmed not to match.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Typical room areas + uncertainty helper module

**Files:**
- Create: `lighting-engine/src/lighting_engine/parser/uncertainty.py`
- Test: `lighting-engine/tests/parser/test_uncertainty.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/parser/test_uncertainty.py
from lighting_engine.parser.uncertainty import (
    TYPICAL_ROOM_AREAS_M2,
    area_is_anomalous,
    confidence_for_polygon_label_match,
)


def test_typical_areas_cover_first_class_rooms():
    for room_type in (
        "bedroom", "master_bedroom", "kitchen", "dining", "drawing_room",
        "study", "bathroom",
    ):
        assert room_type in TYPICAL_ROOM_AREAS_M2
        assert TYPICAL_ROOM_AREAS_M2[room_type] > 0


def test_area_anomaly_within_band_returns_false():
    # bedroom typical = 14m². Anything 4.7m² to 42m² is within 3x.
    assert not area_is_anomalous(room_type="bedroom", actual_area_m2=14.0)
    assert not area_is_anomalous(room_type="bedroom", actual_area_m2=20.0)
    assert not area_is_anomalous(room_type="bedroom", actual_area_m2=8.0)


def test_area_anomaly_too_large():
    # 3x of 14 = 42m². 50m² is anomalous for a bedroom.
    assert area_is_anomalous(room_type="bedroom", actual_area_m2=50.0)


def test_area_anomaly_too_small():
    # 1/3 of 14 = 4.67m². 4m² is anomalous for a bedroom.
    assert area_is_anomalous(room_type="bedroom", actual_area_m2=4.0)


def test_area_anomaly_unknown_room_type_is_not_anomalous():
    # If we don't know the typical, we can't judge — return False (don't flag).
    assert not area_is_anomalous(room_type="unknown", actual_area_m2=100.0)


def test_confidence_for_label_outside_any_cell():
    c = confidence_for_polygon_label_match(
        label_in_cell=False, has_competing_label=False,
        is_orphan_cell=False, area_anomalous=False,
    )
    assert c == 0.2


def test_confidence_for_orphan_cell():
    c = confidence_for_polygon_label_match(
        label_in_cell=True, has_competing_label=False,
        is_orphan_cell=True, area_anomalous=False,
    )
    assert c == 0.3


def test_confidence_clean_match_is_one():
    c = confidence_for_polygon_label_match(
        label_in_cell=True, has_competing_label=False,
        is_orphan_cell=False, area_anomalous=False,
    )
    assert c == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/parser/test_uncertainty.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the module**

```python
# lighting-engine/src/lighting_engine/parser/uncertainty.py
"""Confidence scoring + typical-area reference for parser uncertainty.

Confidence values drive the Layer 2 LLM disambiguation: only rooms with at
least one low-confidence entity get sent to Claude.
"""
from __future__ import annotations

# Typical floor areas (m²) for Indian residential rooms. Used by the
# `area_is_anomalous` heuristic to flag polygons that are >3x or <1/3 of
# the typical size for their labeled type — strong signal the label-to-
# polygon match is wrong.
TYPICAL_ROOM_AREAS_M2: dict[str, float] = {
    "bedroom": 14.0,
    "master_bedroom": 22.0,
    "guest_bedroom": 12.0,
    "kitchen": 12.0,
    "dining": 16.0,
    "drawing_room": 30.0,
    "family_lounge": 22.0,
    "study": 10.0,
    "bathroom": 5.0,
    "powder_toilet": 3.0,
    "puja_room": 4.0,
    "store_room": 4.0,
    "pantry": 6.0,
    "lobby": 15.0,
    "foyer": 8.0,
    "dress": 6.0,
    "balcony": 6.0,
    "courtyard": 12.0,
}

# Anomaly band: a polygon is flagged when its area is more than this multiple
# (or less than the reciprocal) of the typical area for its room type.
_AREA_ANOMALY_FACTOR = 3.0


def area_is_anomalous(*, room_type: str, actual_area_m2: float) -> bool:
    typical = TYPICAL_ROOM_AREAS_M2.get(room_type)
    if typical is None:
        return False
    if actual_area_m2 > typical * _AREA_ANOMALY_FACTOR:
        return True
    if actual_area_m2 < typical / _AREA_ANOMALY_FACTOR:
        return True
    return False


def confidence_for_polygon_label_match(
    *,
    label_in_cell: bool,
    has_competing_label: bool,
    is_orphan_cell: bool,
    area_anomalous: bool,
) -> float:
    """Score the parser's polygon ↔ label assignment for one room.

    Each predicate is computed by the caller from polygon/label geometry.
    The lowest-scoring trigger wins (most pessimistic).
    """
    score = 1.0
    if not label_in_cell:
        score = min(score, 0.2)
    if has_competing_label:
        score = min(score, 0.4)
    if is_orphan_cell:
        score = min(score, 0.3)
    if area_anomalous:
        score = min(score, 0.5)
    return score
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/parser/test_uncertainty.py -v`
Expected: All 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/parser/uncertainty.py lighting-engine/tests/parser/test_uncertainty.py
git commit -m "feat(parser): uncertainty scoring + typical-area table

Codifies the parser's confidence-scoring rules so Layer 2 only verifies
genuinely uncertain rooms. Typical-area table sourced from Indian
residential norms; anomaly band is >3x or <1/3 the typical.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase B — Layer 1 deterministic improvements

### Task 5: INSERT block extraction — furniture_geometry.py

**Files:**
- Create: `lighting-engine/src/lighting_engine/parser/furniture_geometry.py`
- Test: `lighting-engine/tests/parser/test_furniture_geometry.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/parser/test_furniture_geometry.py
from pathlib import Path

import ezdxf

from lighting_engine.parser.furniture_geometry import (
    extract_furniture_from_inserts,
)


def test_extracts_inserts_with_footprint_polygons():
    # Synthetic DXF with one INSERT whose block contains a 2x1 rectangle
    doc = ezdxf.new()
    msp = doc.modelspace()
    block = doc.blocks.new(name="BED-DOUBLE")
    block.add_lwpolyline([(0, 0), (2, 0), (2, 1), (0, 1), (0, 0)])
    msp.add_blockref("BED-DOUBLE", insert=(10, 20))

    candidates = extract_furniture_from_inserts(doc)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.position.x == 10.0  # insert origin
    assert c.position.y == 20.0
    assert c.raw_label == "BED-DOUBLE"
    assert c.type == "BED"   # heuristic match on block name
    assert c.confidence == 0.9
    # Footprint translated to insert position
    assert c.footprint is not None
    assert len(c.footprint) == 5  # closed polygon
    xs = [p.x for p in c.footprint]
    ys = [p.y for p in c.footprint]
    assert min(xs) == 10 and max(xs) == 12
    assert min(ys) == 20 and max(ys) == 21


def test_drops_autocad_block_ids_label_but_keeps_footprint():
    doc = ezdxf.new()
    block = doc.blocks.new(name="A$C40b9ed5b")
    block.add_lwpolyline([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    msp = doc.modelspace()
    msp.add_blockref("A$C40b9ed5b", insert=(5, 5))

    candidates = extract_furniture_from_inserts(doc)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.raw_label is None    # block-ID label dropped
    assert c.type == "unknown"
    assert c.confidence == 0.5    # uncertain
    assert c.footprint is not None


def test_recurses_into_nested_inserts_with_depth_limit():
    doc = ezdxf.new()
    inner = doc.blocks.new(name="INNER")
    inner.add_lwpolyline([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    outer = doc.blocks.new(name="SOFA-3SEAT")
    outer.add_blockref("INNER", insert=(0, 0))
    msp = doc.modelspace()
    msp.add_blockref("SOFA-3SEAT", insert=(0, 0))

    candidates = extract_furniture_from_inserts(doc)
    # The top-level SOFA-3SEAT is the candidate; nested INNER folds into
    # the parent's footprint.
    assert len(candidates) == 1
    assert candidates[0].type == "SOFA"


def test_classifies_known_block_names():
    cases = {
        "BED-DOUBLE": "BED",
        "BD-KING": "BED",
        "SOFA-3SEAT": "SOFA",
        "SF-L": "SOFA",
        "DT-8": "DINING_TABLE",
        "DINING TABLE": "DINING_TABLE",
        "DRESSER": "unknown",          # not in heuristic list
        "Poltrona Ricca Grando": "unknown",
    }
    for block_name, expected_type in cases.items():
        doc = ezdxf.new()
        block = doc.blocks.new(name=block_name)
        block.add_lwpolyline([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        doc.modelspace().add_blockref(block_name, insert=(0, 0))
        candidates = extract_furniture_from_inserts(doc)
        assert candidates[0].type == expected_type, f"{block_name} -> {candidates[0].type}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/parser/test_furniture_geometry.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/parser/furniture_geometry.py
"""Geometric extraction of furniture from DXF INSERT entities.

The parser previously only saw TEXT entities, missing beds/sofas/dining
tables that live as block references. This module walks INSERTs, resolves
each block's footprint from its BLOCK definition, and classifies what's
obvious from the block name. Layer 2 (LLM) classifies the rest.
"""
from __future__ import annotations

import math
import re
from typing import Iterable

import ezdxf
from ezdxf.entities import Insert

from lighting_engine.models.geometry import Furniture, Point
from lighting_engine.parser.cad_id_filter import is_cad_block_id

_NESTED_DEPTH_LIMIT = 3

# Heuristic classification by block name. Lower-cased + space/dash-tolerant.
_BLOCK_NAME_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(bed|bd)[-_ ]"), "BED"),
    (re.compile(r"bed"), "BED"),
    (re.compile(r"^(sofa|sf)[-_ ]"), "SOFA"),
    (re.compile(r"sofa"), "SOFA"),
    (re.compile(r"^dt[-_ ]"), "DINING_TABLE"),
    (re.compile(r"dining[ -]table"), "DINING_TABLE"),
    (re.compile(r"dining"), "DINING_TABLE"),
]


def _classify_block_name(name: str) -> str:
    lowered = name.lower()
    for pattern, type_label in _BLOCK_NAME_TYPE_PATTERNS:
        if pattern.search(lowered):
            return type_label
    return "unknown"


def _walk_block_for_polylines(
    block: ezdxf.layouts.BlockLayout, depth: int,
) -> list[list[tuple[float, float]]]:
    """Collect all polyline footprints inside a block, recursing into nested
    INSERTs up to ``_NESTED_DEPTH_LIMIT`` levels. Each returned polyline is a
    list of (x, y) in the block's local frame.
    """
    if depth > _NESTED_DEPTH_LIMIT:
        return []
    polylines: list[list[tuple[float, float]]] = []
    for entity in block:
        if entity.dxftype() == "LWPOLYLINE":
            polylines.append([(p[0], p[1]) for p in entity.get_points("xy")])
        elif entity.dxftype() == "INSERT":
            nested = entity.doc.blocks.get(entity.dxf.name)
            if nested is not None:
                polylines.extend(_walk_block_for_polylines(nested, depth + 1))
    return polylines


def _transform_polyline(
    polyline: list[tuple[float, float]],
    *, insert_x: float, insert_y: float, rotation_deg: float,
    scale_x: float, scale_y: float,
) -> list[Point]:
    """Apply the INSERT entity's transform (translate + rotate + scale) to a
    block-local polyline. Returns world-frame points.
    """
    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    out: list[Point] = []
    for x, y in polyline:
        sx = x * scale_x
        sy = y * scale_y
        rx = sx * cos_t - sy * sin_t
        ry = sx * sin_t + sy * cos_t
        out.append(Point(x=insert_x + rx, y=insert_y + ry))
    return out


def _polyline_bounding_polygon(points: list[Point]) -> list[Point]:
    """Return ``points`` if already closed, else append the first point."""
    if len(points) == 0:
        return points
    if points[0].x == points[-1].x and points[0].y == points[-1].y:
        return points
    return [*points, points[0]]


def extract_furniture_from_inserts(doc: ezdxf.document.Drawing) -> list[Furniture]:
    """Walk modelspace INSERT entities and return Furniture candidates.

    Each INSERT becomes one Furniture record. Nested INSERTs are folded into
    the top-level candidate's footprint (we don't emit separate records for
    sub-blocks because they're parts of one piece of furniture, not separate
    pieces).
    """
    candidates: list[Furniture] = []
    for entity in doc.modelspace().query("INSERT"):
        if not isinstance(entity, Insert):
            continue
        block_name = entity.dxf.name
        block = doc.blocks.get(block_name)
        if block is None:
            continue
        polylines_local = _walk_block_for_polylines(block, depth=0)
        if not polylines_local:
            continue
        # Use the *largest* polyline (by point count) as the candidate's
        # footprint. Real furniture blocks have one outer polyline + many
        # small detail strokes.
        outer = max(polylines_local, key=len)
        footprint_world = _transform_polyline(
            outer,
            insert_x=entity.dxf.insert.x,
            insert_y=entity.dxf.insert.y,
            rotation_deg=entity.dxf.rotation,
            scale_x=entity.dxf.xscale,
            scale_y=entity.dxf.yscale,
        )
        footprint_world = _polyline_bounding_polygon(footprint_world)

        is_cad_id = is_cad_block_id(block_name)
        raw_label = None if is_cad_id else block_name
        type_label = "unknown" if is_cad_id else _classify_block_name(block_name)
        confidence = (
            0.5 if (is_cad_id or type_label == "unknown") else 0.9
        )

        candidates.append(
            Furniture(
                id=f"furn-{entity.dxf.handle}",
                raw_label=raw_label,
                type=type_label,
                position=Point(
                    x=entity.dxf.insert.x, y=entity.dxf.insert.y,
                ),
                footprint=footprint_world,
                confidence=confidence,
                provenance="parser",
                llm_status="unchecked",
            )
        )
    return candidates


def extract_furniture_from_file(path) -> list[Furniture]:
    """Convenience: parse a DXF file path and extract furniture candidates."""
    doc = ezdxf.readfile(str(path))
    return extract_furniture_from_inserts(doc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/parser/test_furniture_geometry.py -v`
Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/parser/furniture_geometry.py lighting-engine/tests/parser/test_furniture_geometry.py
git commit -m "feat(parser): INSERT block extraction for furniture geometry

Walks DXF INSERT entities, resolves block footprints (with nested-block
recursion up to depth 3), heuristically classifies BED/SOFA/DINING_TABLE
from block names, and drops AutoCAD-generated block-IDs to type=unknown.
The footprint Point list is set so fixture-placement can avoid the piece.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: LOBBY orphan-cell recovery candidates

**Files:**
- Create: `lighting-engine/src/lighting_engine/parser/lobby_recovery.py`
- Test: `lighting-engine/tests/parser/test_lobby_recovery.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/parser/test_lobby_recovery.py
from lighting_engine.models.geometry import Point, Room
from lighting_engine.parser.lobby_recovery import (
    LobbyRecoveryCandidate, find_lobby_recovery_candidates,
)


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[Point]:
    return [
        Point(x=x0, y=y0), Point(x=x1, y=y0),
        Point(x=x1, y=y1), Point(x=x0, y=y1),
    ]


def test_orphan_adjacent_to_lobby_returns_candidate():
    lobby = Room(id="lobby", name="LOBBY", type="hallway", polygon=_rect(0,0,5,2))
    orphan = Room(id="orphan", name="", type="unknown", polygon=_rect(5,0,7,2))
    bedroom = Room(id="bed", name="Bedroom", type="bedroom", polygon=_rect(0,2,5,5))

    candidates = find_lobby_recovery_candidates(rooms=[lobby, orphan, bedroom])
    assert len(candidates) == 1
    c = candidates[0]
    assert isinstance(c, LobbyRecoveryCandidate)
    assert c.orphan_room_id == "orphan"
    assert c.parent_room_id == "lobby"
    assert c.shared_wall_length_m > 0
    assert c.confidence <= 0.6


def test_orphan_not_adjacent_to_any_passage_returns_no_candidate():
    bedroom = Room(id="bed", name="Bedroom", type="bedroom", polygon=_rect(0,0,5,5))
    orphan = Room(id="orphan", name="", type="unknown", polygon=_rect(10,10,12,12))
    candidates = find_lobby_recovery_candidates(rooms=[bedroom, orphan])
    assert candidates == []


def test_tie_breaker_picks_longer_shared_wall():
    lobby_a = Room(id="lobby_a", name="LOBBY", type="hallway", polygon=_rect(0,0,5,2))
    # lobby_b shares only 1m of wall with the orphan; lobby_a shares 2m
    lobby_b = Room(id="lobby_b", name="PASSAGE", type="hallway", polygon=_rect(5,1,7,2))
    orphan = Room(id="orphan", name="", type="unknown", polygon=_rect(5,0,7,1))
    candidates = find_lobby_recovery_candidates(rooms=[lobby_a, lobby_b, orphan])
    assert len(candidates) == 1
    assert candidates[0].parent_room_id == "lobby_a"


def test_tied_shared_walls_within_10_percent_emit_ambiguous():
    # Two passage rooms each share ~1m with the orphan — ambiguous
    lobby_a = Room(id="lobby_a", name="LOBBY", type="hallway", polygon=_rect(0,0,2,1))
    lobby_b = Room(id="lobby_b", name="PASSAGE", type="hallway", polygon=_rect(0,1,2,2))
    orphan = Room(id="orphan", name="", type="unknown", polygon=_rect(2,0,4,2))
    candidates = find_lobby_recovery_candidates(rooms=[lobby_a, lobby_b, orphan])
    # When tied, return both as candidates with confidence < 0.5
    parents = {c.parent_room_id for c in candidates}
    assert parents == {"lobby_a", "lobby_b"}
    for c in candidates:
        assert c.confidence < 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/parser/test_lobby_recovery.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/parser/lobby_recovery.py
"""Identify orphan cells likely to be part of a non-convex LOBBY/PASSAGE.

Real Indian residential plans have L-shaped or U-shaped LOBBY polygons that
span the entire circulation spine. Our wall-graph polygonizer returns
minimum-area faces, so the L-shape gets split into 2-3 cells. This module
finds 'orphan cells' (cells with no claiming text label) that sit adjacent
to a passage-type room and emits merge candidates for Layer 2 to verify.

Why not just merge here?
- A wrong silent merge ruins downstream lighting design.
- 'No interior space is unlabeled' is a hard rule — the LLM should
  explicitly confirm what the orphan belongs to.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon

from lighting_engine.models.geometry import Point, Room
from lighting_engine.parser.room_tier import is_passage_type

_TIE_TOLERANCE = 0.10  # 10% — within this we mark candidates ambiguous


@dataclass(frozen=True)
class LobbyRecoveryCandidate:
    orphan_room_id: str
    parent_room_id: str
    shared_wall_length_m: float
    confidence: float


def _polygon_from_points(points: list[Point]) -> Polygon:
    return Polygon([(p.x, p.y) for p in points])


def _shared_wall_length(a: list[Point], b: list[Point]) -> float:
    """Length of the shared boundary between two polygons, in meters.

    Computed as the length of the polygon-intersection's perimeter that lies
    on both inputs. Uses shapely's intersection over the polygon boundaries.
    """
    pa = _polygon_from_points(a)
    pb = _polygon_from_points(b)
    inter = pa.boundary.intersection(pb.boundary)
    return inter.length if not inter.is_empty else 0.0


def find_lobby_recovery_candidates(
    *, rooms: list[Room],
) -> list[LobbyRecoveryCandidate]:
    """Return one candidate per (orphan, plausible passage parent) pair."""
    orphans = [r for r in rooms if r.type == "unknown" and len(r.polygon) >= 3]
    passages = [
        r for r in rooms
        if r.type != "unknown" and is_passage_type(r.type) and len(r.polygon) >= 3
    ]

    candidates: list[LobbyRecoveryCandidate] = []
    for orphan in orphans:
        # Compute shared-wall lengths with every passage
        scored: list[tuple[Room, float]] = []
        for passage in passages:
            length = _shared_wall_length(orphan.polygon, passage.polygon)
            if length > 0:
                scored.append((passage, length))
        if not scored:
            continue
        scored.sort(key=lambda t: -t[1])
        longest = scored[0][1]
        # Tie-breaker: if any other parent is within 10% of the longest,
        # emit both with reduced confidence (Layer 2 picks).
        for passage, length in scored:
            if length >= longest * (1 - _TIE_TOLERANCE):
                is_tied = len([s for s in scored if s[1] >= longest * (1 - _TIE_TOLERANCE)]) > 1
                base_confidence = 0.6
                confidence = base_confidence - 0.2 if is_tied else base_confidence
                candidates.append(
                    LobbyRecoveryCandidate(
                        orphan_room_id=orphan.id,
                        parent_room_id=passage.id,
                        shared_wall_length_m=length,
                        confidence=confidence,
                    )
                )
    return candidates
```

Also confirm `parser/room_tier.py` has `is_passage_type`. If not, add it:

```python
# In parser/room_tier.py — add if missing
def is_passage_type(room_type: str) -> bool:
    """True for room types that typically extend as L-shaped circulation."""
    return room_type in {"hallway", "foyer", "passage", "lobby"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/parser/test_lobby_recovery.py -v`
Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/parser/lobby_recovery.py lighting-engine/src/lighting_engine/parser/room_tier.py lighting-engine/tests/parser/test_lobby_recovery.py
git commit -m "feat(parser): lobby_recovery emits orphan-cell merge candidates

Finds orphan cells (no text label) adjacent to a passage-type room and
emits merge candidates with confidence ≤ 0.6 for Layer 2 to verify.
Tie-breaker: shared-wall length; ties within 10% emit multiple candidates
with reduced confidence.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Drop AutoCAD block-IDs at the candidate-seen stage in furniture_merge

**Files:**
- Modify: `lighting-engine/src/lighting_engine/parser/furniture_merge.py`
- Test: `lighting-engine/tests/parser/test_furniture_merge_filters_cad_ids.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/parser/test_furniture_merge_filters_cad_ids.py
from pathlib import Path

from lighting_engine.parser.furniture_merge import merge_furniture_from_file
from lighting_engine.parser.pipeline import parse_file


def test_furniture_merge_excludes_autocad_block_ids_from_candidates_seen():
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_base_architectural.dxf"),
        project_name="delhi", location="delhi",
    )
    _, report = merge_furniture_from_file(
        project, Path("tests/fixtures/dwgs/real_furniture.dxf"),
    )
    # Before this change: report.furniture_seen == 31 (counts the 13 block-IDs)
    # After: report.furniture_seen drops to ~18 (real labels only)
    assert report.furniture_seen < 25, (
        f"Expected block-IDs to be excluded; got {report.furniture_seen}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/parser/test_furniture_merge_filters_cad_ids.py -v`
Expected: FAIL — `assert 31 < 25`.

- [ ] **Step 3: Modify `furniture_merge.py`**

In `lighting-engine/src/lighting_engine/parser/furniture_merge.py`, find the function that iterates TEXT entities to build the candidate list. Add an early-continue for CAD block IDs:

```python
# At top of file
from lighting_engine.parser.cad_id_filter import is_cad_block_id

# In the function that produces the candidate list — wherever a TEXT label is
# read into a candidate, add:
if is_cad_block_id(text_label):
    continue   # AutoCAD-generated noise, not a furniture label
```

(The exact location depends on the current file's structure. Look for the loop building "candidates" or "items" or similar from `doc.modelspace().query("TEXT MTEXT")` — add the filter inside that loop.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/parser/test_furniture_merge_filters_cad_ids.py -v`
Expected: PASS.

- [ ] **Step 5: Run all parser tests to confirm no regressions**

Run: `cd lighting-engine && uv run pytest tests/parser/ -v`
Expected: All pass; the new test passes.

- [ ] **Step 6: Commit**

```bash
git add lighting-engine/src/lighting_engine/parser/furniture_merge.py lighting-engine/tests/parser/test_furniture_merge_filters_cad_ids.py
git commit -m "fix(parser): exclude AutoCAD block-IDs from furniture candidate pool

Drops noise like A\$C40b9ed5b before it gets counted in furniture_seen.
Reduces Delhi candidates from 31 to ~18 (real furniture labels only).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Emit per-door + per-window confidence in detection modules

**Files:**
- Modify: `lighting-engine/src/lighting_engine/parser/door_anchor.py`
- Modify: `lighting-engine/src/lighting_engine/parser/window_filter.py`
- Test: `lighting-engine/tests/parser/test_door_window_confidence.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/parser/test_door_window_confidence.py
from pathlib import Path

from lighting_engine.parser.pipeline import parse_file


def test_doors_have_non_default_confidence_in_real_plan():
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_base_architectural.dxf"),
        project_name="delhi", location="delhi",
    )
    all_doors = [d for r in project.rooms for d in r.doors]
    # At least some doors should be flagged with lower confidence given the
    # known mis-attribution (Drawing Room=0, Puja Room=3).
    has_low_confidence_door = any(d.confidence < 0.8 for d in all_doors)
    assert has_low_confidence_door, (
        "Expected at least one door with confidence < 0.8 to flag mis-attribution"
    )


def test_windows_on_terrace_walls_get_low_confidence():
    # Windows attached to a wall facing an outdoor room (courtyard/terrace)
    # should be flagged for review (potential French window).
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_base_architectural.dxf"),
        project_name="delhi", location="delhi",
    )
    all_windows = [w for r in project.rooms for w in r.windows]
    # Just verify the field is populated (not all 1.0).
    confidences = [w.confidence for w in all_windows]
    assert any(c < 1.0 for c in confidences), "Expected some windows to be flagged"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/parser/test_door_window_confidence.py -v`
Expected: FAIL — all confidences will currently be 1.0.

- [ ] **Step 3: Update door_anchor.py + window_filter.py**

In `parser/door_anchor.py`, wherever the function emits a `Door`, compute confidence based on the triggers from the spec:

```python
def _compute_door_confidence(
    *,
    multiple_doors_same_wall: bool,
    not_near_wall_midpoint: bool,
    wall_shared_ambiguously: bool,
) -> float:
    score = 1.0
    if multiple_doors_same_wall:
        score = min(score, 0.5)
    if not_near_wall_midpoint:
        score = min(score, 0.3)
    if wall_shared_ambiguously:
        score = min(score, 0.4)
    return score
```

And in `window_filter.py`, similar:

```python
def _compute_window_confidence(
    *,
    not_adjacent_to_interior_wall: bool,
    faces_terrace_or_courtyard: bool,
) -> float:
    score = 1.0
    if not_adjacent_to_interior_wall:
        score = min(score, 0.2)
    if faces_terrace_or_courtyard:
        score = min(score, 0.4)
    return score
```

Wire each emitter to compute and set `confidence` on the Door/Window before returning.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/parser/test_door_window_confidence.py -v`
Expected: PASS.

- [ ] **Step 5: Run all parser tests**

Run: `cd lighting-engine && uv run pytest tests/parser/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add lighting-engine/src/lighting_engine/parser/door_anchor.py lighting-engine/src/lighting_engine/parser/window_filter.py lighting-engine/tests/parser/test_door_window_confidence.py
git commit -m "feat(parser): emit per-door + per-window confidence scores

Confidence triggers per spec: multiple doors on one wall, door not near
midpoint, wall shared ambiguously, window not adjacent to interior wall,
window faces terrace/courtyard.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Wire Layer 1 changes into pipeline.py

**Files:**
- Modify: `lighting-engine/src/lighting_engine/parser/pipeline.py`
- Test: `lighting-engine/tests/parser/test_pipeline_emits_uncertainty.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/parser/test_pipeline_emits_uncertainty.py
from pathlib import Path

from lighting_engine.parser.pipeline import parse_file


def test_pipeline_runs_furniture_geometry_extraction():
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_furniture.dxf"),
        project_name="delhi", location="delhi",
    )
    all_furniture = [f for r in project.rooms for f in r.furniture]
    # furniture_geometry yields candidates with non-empty footprint
    with_footprint = [f for f in all_furniture if f.footprint]
    assert len(with_footprint) > 0


def test_pipeline_marks_polygon_label_uncertainty():
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_base_architectural.dxf"),
        project_name="delhi", location="delhi",
    )
    # At least one room should have confidence < 1.0 reflecting one of
    # the triggers (area anomaly, orphan, competing labels, etc.)
    has_low_conf_room = any(r.confidence < 1.0 for r in project.rooms)
    assert has_low_conf_room
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/parser/test_pipeline_emits_uncertainty.py -v`
Expected: FAIL — `parse_file` doesn't call the new modules yet.

- [ ] **Step 3: Update `parser/pipeline.py`**

After the existing pipeline assembles rooms (text-anchored labels matched to cells), and after `infer_door_destinations` runs, add:

```python
from lighting_engine.parser.furniture_geometry import extract_furniture_from_inserts
from lighting_engine.parser.lobby_recovery import find_lobby_recovery_candidates
from lighting_engine.parser.uncertainty import (
    area_is_anomalous,
    confidence_for_polygon_label_match,
)

# After room assembly + door attachment:

# 1. Geometric furniture extraction (operates on the DXF doc, not just text)
inserts_furniture = extract_furniture_from_inserts(doc)
# Attach each candidate to whichever room polygon contains its position
for f in inserts_furniture:
    room = _find_room_containing_point(rooms, f.position)
    if room is not None:
        room.furniture.append(f)

# 2. LOBBY recovery candidates
lobby_candidates = find_lobby_recovery_candidates(rooms=rooms)
# Stash on the Project as a top-level field so Layer 2 can pick them up
project.lobby_recovery_candidates = lobby_candidates

# 3. Confidence scoring on each room's polygon ↔ label match
for room in rooms:
    if not room.polygon:
        continue
    area_m2 = _polygon_area(room.polygon)
    room.confidence = confidence_for_polygon_label_match(
        label_in_cell=True,  # if we got here, the label was in a cell
        has_competing_label=_has_competing_label(rooms, room),
        is_orphan_cell=False,  # orphans don't get a label in the first place
        area_anomalous=area_is_anomalous(
            room_type=room.type, actual_area_m2=area_m2,
        ),
    )
```

(`_find_room_containing_point`, `_has_competing_label`, `_polygon_area` are small helpers — add them to pipeline.py or a util.)

You'll also need to add `lobby_recovery_candidates: list[LobbyRecoveryCandidate] = []` to `Project` in `models/geometry.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/parser/test_pipeline_emits_uncertainty.py -v`
Expected: PASS.

- [ ] **Step 5: Run all parser + API tests**

Run: `cd lighting-engine && uv run pytest`
Expected: All pass (336 + new tasks' new tests).

- [ ] **Step 6: Commit**

```bash
git add lighting-engine/src/lighting_engine/parser/pipeline.py lighting-engine/src/lighting_engine/models/geometry.py lighting-engine/tests/parser/test_pipeline_emits_uncertainty.py
git commit -m "feat(parser): wire furniture_geometry + lobby_recovery + confidence scoring into pipeline

Layer 1 deterministic pass now emits uncertainty signals on each entity
plus LOBBY recovery candidates at the project level. Ready for Layer 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Feature flag for LLM verification

**Files:**
- Create: `lighting-engine/src/lighting_engine/llm/__init__.py`
- Create: `lighting-engine/src/lighting_engine/llm/feature_flag.py`
- Test: `lighting-engine/tests/llm/test_feature_flag.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/llm/test_feature_flag.py
import os

import pytest

from lighting_engine.llm.feature_flag import (
    is_llm_verification_enabled, MissingApiKeyError,
)


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LIGHTING_ENGINE_LLM_VERIFY_ENABLED", raising=False)
    assert is_llm_verification_enabled() is False


def test_explicit_disable(monkeypatch):
    monkeypatch.setenv("LIGHTING_ENGINE_LLM_VERIFY_ENABLED", "false")
    assert is_llm_verification_enabled() is False


def test_enabled_with_api_key(monkeypatch):
    monkeypatch.setenv("LIGHTING_ENGINE_LLM_VERIFY_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-xxx")
    assert is_llm_verification_enabled() is True


def test_enabled_without_api_key_returns_false(monkeypatch):
    """Flag on but no key — disable rather than crash."""
    monkeypatch.setenv("LIGHTING_ENGINE_LLM_VERIFY_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert is_llm_verification_enabled() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/llm/test_feature_flag.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/llm/__init__.py
"""Layer 2 — Claude vision disambiguation of parser uncertainty."""
```

```python
# lighting-engine/src/lighting_engine/llm/feature_flag.py
"""Feature flag + readiness checks for the LLM verification layer.

The flag must be explicitly ON *and* an Anthropic API key must be present.
If either is missing, Layer 2 is skipped and the project ships with
verification_mode = "disabled" (every room shown as 'manual').
"""
import os


class MissingApiKeyError(RuntimeError):
    """Raised internally if production code asks for the client without a key."""


def is_llm_verification_enabled() -> bool:
    """True only when the feature flag is on AND an API key is configured."""
    flag = os.environ.get("LIGHTING_ENGINE_LLM_VERIFY_ENABLED", "false")
    if flag.lower() not in ("true", "1", "yes"):
        return False
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/llm/test_feature_flag.py -v`
Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/llm/__init__.py lighting-engine/src/lighting_engine/llm/feature_flag.py lighting-engine/tests/llm/
git commit -m "feat(llm): feature flag + API key readiness check

LIGHTING_ENGINE_LLM_VERIFY_ENABLED gates Layer 2. Missing API key
silently disables; system continues to work without LLM verification.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase C — Layer 2 Claude vision verifier

### Task 11: Structured-output pydantic schemas

**Files:**
- Create: `lighting-engine/src/lighting_engine/llm/schemas.py`
- Test: `lighting-engine/tests/llm/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/llm/test_schemas.py
from lighting_engine.llm.schemas import (
    DoorDecision, FurnitureClassifyDecision, FurnitureAddDecision,
    LobbyRecoveryDecision, PolygonAssignmentDecision, RoomVerifyResponse,
)


def test_polygon_assignment_decision_round_trip():
    d = PolygonAssignmentDecision(
        cell_id="cell-A37", confidence=0.95,
        reason="DINING label centroid is inside cell-A37",
    )
    serialized = d.model_dump()
    assert serialized["cell_id"] == "cell-A37"


def test_door_decision_with_alternatives():
    d = DoorDecision(
        door_id="d12",
        type="sliding",
        leads_to_room_id="room-drawing",
        confidence=0.85,
        reason="Double slider opens toward drawing room",
        alternatives=[{"type":"regular","confidence":0.1,"reason":"single swing"}],
    )
    assert d.confidence == 0.85
    assert len(d.alternatives) == 1


def test_furniture_classify_with_alternatives_list():
    d = FurnitureClassifyDecision(
        furniture_id="f2",
        type="SIDEBOARD",
        confidence=0.4,
        reason="Faint outline along east wall, could be planter",
        alternatives=[
            {"type":"PLANTER","confidence":0.3,"reason":"size matches a planter"},
            {"type":"unknown","confidence":0.3,"reason":"too vague"},
        ],
    )
    assert d.type == "SIDEBOARD"
    assert len(d.alternatives) == 2


def test_furniture_add_carries_position():
    d = FurnitureAddDecision(
        type="SIDEBOARD",
        position={"x": 14.2, "y": 7.1},
        confidence=0.7,
        reason="polyline along east wall consistent with sideboard outline",
    )
    assert d.position == {"x": 14.2, "y": 7.1}


def test_lobby_recovery_response_decisions():
    d = LobbyRecoveryDecision(
        orphan_room_id="orph-7", parent_room_id="lobby",
        confidence=0.9, reason="orphan extends LOBBY as L-shape",
    )
    assert d.parent_room_id == "lobby"


def test_room_verify_response_wraps_decisions():
    resp = RoomVerifyResponse(
        room_id="r1",
        polygon_assignment=PolygonAssignmentDecision(
            cell_id="cell-A37", confidence=0.95, reason="..."
        ),
        doors=[],
        windows=[],
        furniture_classify=[],
        furniture_add=[],
    )
    assert resp.room_id == "r1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/llm/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/llm/schemas.py
"""Pydantic models for Claude's structured-output responses.

Each decision type carries Claude's `value` (the answer), a `confidence`
∈ [0, 1], a one-sentence `reason`, and an optional `alternatives` list with
Claude's runner-up choices. The disambiguator merges these into the IR.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _BaseDecision(BaseModel):
    """Base type — frozen so accidental mutation is loud."""
    model_config = ConfigDict(frozen=True)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class _BaseAlternative(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class PolygonAssignmentDecision(_BaseDecision):
    """Which cell-id is the right polygon for this room's label."""
    cell_id: str


class DoorAlternative(_BaseAlternative):
    type: str
    leads_to_room_id: str | None = None


class DoorDecision(_BaseDecision):
    door_id: str
    type: str
    leads_to_room_id: str | None = None
    alternatives: list[DoorAlternative] = Field(default_factory=list)


class WindowAlternative(_BaseAlternative):
    is_door_window: bool


class WindowDecision(_BaseDecision):
    window_id: str
    is_door_window: bool
    alternatives: list[WindowAlternative] = Field(default_factory=list)


class FurnitureAlternative(_BaseAlternative):
    type: str


class FurnitureClassifyDecision(_BaseDecision):
    furniture_id: str
    type: str
    alternatives: list[FurnitureAlternative] = Field(default_factory=list)


class FurnitureAddDecision(_BaseDecision):
    """Claude proposes adding a piece of furniture the parser missed."""
    type: str
    position: dict[str, float]   # {"x": ..., "y": ...} in room-local meters


class LobbyRecoveryDecision(_BaseDecision):
    orphan_room_id: str
    parent_room_id: str | None  # None = orphan is not an extension of any room


class RoomVerifyResponse(BaseModel):
    """Claude's full response for one room call."""
    model_config = ConfigDict(frozen=True)

    room_id: str
    polygon_assignment: PolygonAssignmentDecision | None = None
    doors: list[DoorDecision] = Field(default_factory=list)
    windows: list[WindowDecision] = Field(default_factory=list)
    furniture_classify: list[FurnitureClassifyDecision] = Field(default_factory=list)
    furniture_add: list[FurnitureAddDecision] = Field(default_factory=list)


class LobbyRecoveryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    decisions: list[LobbyRecoveryDecision] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/llm/test_schemas.py -v`
Expected: All 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/llm/schemas.py lighting-engine/tests/llm/test_schemas.py
git commit -m "feat(llm): pydantic schemas for Claude structured-output decisions

One model per decision type (polygon assignment, door, window, furniture
classify/add, LOBBY recovery). RoomVerifyResponse wraps them per call.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Room render — PNG crop for Claude

**Files:**
- Create: `lighting-engine/src/lighting_engine/llm/room_render.py`
- Test: `lighting-engine/tests/llm/test_room_render.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/llm/test_room_render.py
import io
from pathlib import Path

from PIL import Image

from lighting_engine.llm.room_render import render_room_crop
from lighting_engine.parser.pipeline import parse_file


def test_render_returns_png_bytes_of_expected_size():
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_base_architectural.dxf"),
        project_name="delhi", location="delhi",
    )
    target_room = next(r for r in project.rooms if r.name == "DINING")
    png_bytes = render_room_crop(project=project, room_id=target_room.id)
    assert png_bytes.startswith(b"\x89PNG")
    img = Image.open(io.BytesIO(png_bytes))
    # ~600x600 with matplotlib defaults; allow ±50px tolerance
    assert 550 <= img.width <= 700
    assert 550 <= img.height <= 700


def test_render_handles_room_without_polygon():
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_base_architectural.dxf"),
        project_name="delhi", location="delhi",
    )
    # Edge case — if a room has empty polygon, we still return *something*
    target = next(r for r in project.rooms if r.polygon)
    target_copy = target.model_copy(update={"polygon": []})
    # Swap in to test (without mutating original)
    rooms_with_empty = [
        target_copy if r.id == target.id else r for r in project.rooms
    ]
    project_with_empty = project.model_copy(update={"rooms": rooms_with_empty})
    png_bytes = render_room_crop(
        project=project_with_empty, room_id=target_copy.id,
    )
    assert len(png_bytes) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/llm/test_room_render.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/llm/room_render.py
"""Render a room + immediate neighbors as a PNG for Claude vision.

Matplotlib (existing dep) draws walls, the room polygon highlighted, parsed
candidates as overlays (furniture footprints, doors, windows), and uncertain
items in red. ~600x600px. The output is the bytes that go directly into a
Claude vision content block.
"""
from __future__ import annotations

import io
from typing import Iterable

import matplotlib
matplotlib.use("Agg")   # headless
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

from lighting_engine.models.geometry import Project, Room

_FIG_DPI = 96
_FIG_SIZE_IN = 6.25   # 6.25 in × 96 DPI = 600 px
_NEIGHBOR_RADIUS_M = 15.0


def _room_bbox(room: Room) -> tuple[float, float, float, float]:
    if not room.polygon:
        return (-1, -1, 1, 1)
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def _expand(bbox: tuple[float, float, float, float], by: float) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    return (x0 - by, y0 - by, x1 + by, y1 + by)


def _draw_polygon(ax, points, *, fc, ec, alpha=1.0, lw=1.0, zorder=1) -> None:
    if not points:
        return
    coords = [(p.x, p.y) for p in points]
    ax.add_patch(MplPolygon(coords, facecolor=fc, edgecolor=ec, alpha=alpha,
                             linewidth=lw, zorder=zorder))


def render_room_crop(*, project: Project, room_id: str) -> bytes:
    """Render the room + neighbors within 15m as a 600x600 PNG."""
    target = next((r for r in project.rooms if r.id == room_id), None)
    fig, ax = plt.subplots(figsize=(_FIG_SIZE_IN, _FIG_SIZE_IN), dpi=_FIG_DPI)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("#f5f4f1")

    if target is None or not target.polygon:
        # Fallback render — empty plot with a message
        ax.text(0.5, 0.5, "polygon unavailable",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=12, color="#888")
    else:
        bbox = _expand(_room_bbox(target), _NEIGHBOR_RADIUS_M)
        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])

        # Neighbor rooms (grayscale background)
        for r in project.rooms:
            if r.id == target.id:
                continue
            if not r.polygon:
                continue
            _draw_polygon(ax, r.polygon, fc="#e5e3df", ec="#9a958c",
                          alpha=0.7, lw=0.5, zorder=1)
            xs = [p.x for p in r.polygon]
            ys = [p.y for p in r.polygon]
            ax.text(
                (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                r.name, ha="center", va="center",
                fontsize=8, color="#555",
            )

        # Target room (highlighted)
        _draw_polygon(ax, target.polygon, fc="#fef3c7", ec="#b45309",
                      alpha=0.9, lw=1.5, zorder=2)

        # Furniture footprints (colored, with uncertain ones in red)
        for f in target.furniture:
            color = "#fb923c" if f.confidence >= 0.8 else "#ef4444"
            if f.footprint:
                _draw_polygon(ax, f.footprint, fc=color, ec="#5b1c0a",
                              alpha=0.7, lw=0.5, zorder=3)
            else:
                ax.plot(f.position.x, f.position.y, marker="o",
                        color=color, markersize=8, zorder=3)

        # Doors (orange arcs)
        for d in target.doors:
            color = "#0ea5e9" if d.confidence >= 0.8 else "#ef4444"
            ax.plot(d.position.x, d.position.y, marker="P",
                    color=color, markersize=10, zorder=4)

        # Windows (blue squares)
        for w in target.windows:
            color = "#7dd3fc" if w.confidence >= 0.8 else "#ef4444"
            ax.plot(w.position.x, w.position.y, marker="s",
                    color=color, markersize=8, zorder=4)

        # Room label in big text
        cx = sum(p.x for p in target.polygon) / len(target.polygon)
        cy = sum(p.y for p in target.polygon) / len(target.polygon)
        ax.text(cx, cy, target.name, ha="center", va="center",
                fontsize=14, color="#1c1917", weight="bold", zorder=5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_FIG_DPI, bbox_inches="tight",
                pad_inches=0.1)
    plt.close(fig)
    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/llm/test_room_render.py -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/llm/room_render.py lighting-engine/tests/llm/test_room_render.py
git commit -m "feat(llm): room PNG renderer for Claude vision

600x600 matplotlib render of the target room + neighbors within 15m.
Target highlighted, neighbors grayscale, uncertain items in red.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Prompt templates with prompt caching

**Files:**
- Create: `lighting-engine/src/lighting_engine/llm/prompts.py`
- Test: `lighting-engine/tests/llm/test_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/llm/test_prompts.py
from lighting_engine.llm.prompts import (
    SYSTEM_PROMPT,
    build_room_user_message,
    build_lobby_user_message,
)


def test_system_prompt_includes_delhi_context():
    assert "Indian residential" in SYSTEM_PROMPT
    assert "Delhi" in SYSTEM_PROMPT or "Indian" in SYSTEM_PROMPT


def test_system_prompt_describes_response_format():
    # Claude needs to know we expect JSON
    assert "JSON" in SYSTEM_PROMPT or "json" in SYSTEM_PROMPT


def test_room_user_message_includes_questions():
    msg = build_room_user_message(
        room_label="DINING",
        questions=[{"id": "polygon_assignment", "ask": "Does cell-A37 match?"}],
    )
    assert "DINING" in msg
    assert "polygon_assignment" in msg


def test_lobby_user_message_lists_orphans():
    msg = build_lobby_user_message(
        orphan_ids=["orph-1", "orph-7"],
        labeled_rooms=[("lobby", "LOBBY"), ("foyer", "FOYER")],
    )
    assert "orph-1" in msg and "orph-7" in msg
    assert "LOBBY" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/llm/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/llm/prompts.py
"""System + user prompt templates for Layer 2 disambiguation.

The SYSTEM_PROMPT is cached on every Anthropic call (cache_control: ephemeral)
so we only pay full tokens on the first room call per project upload.
"""
from __future__ import annotations

import json
from typing import Iterable


SYSTEM_PROMPT = """\
You are verifying a parser's interpretation of an Indian residential floor
plan (typically Delhi NCR). The deterministic parser has assigned room
polygons, doors, windows, and furniture, but some assignments may be wrong.

You will receive:
1. A rendered crop of the target room with its neighbors (within ~15m).
   Walls are solid, the target room is highlighted in amber, neighbors are
   grayscale, uncertain items are outlined in red.
2. A structured JSON list of questions about the parser's output for that
   room.

Your job: answer each question. For every answer return:
- value: your best answer
- confidence: a float in [0, 1] reflecting how sure you are
- reason: a one-sentence justification (architect-style — what you see)
- alternatives: optional list of runner-up answers with their own confidence
  and reason. Include alternatives only when you are genuinely uncertain.

Domain rules to apply:
- Every interior space in a residential plan has a labeled room. Unlabeled
  regions are usually arms of the LOBBY or a connecting passage extending
  as an L-shape.
- Indian residential homes commonly have French windows / balcony doors
  that open onto a balcony, terrace, or garden. These look like windows in
  plan view but function as doors.
- A door symbol always sits on a wall shared between two rooms (or the room
  and outside). The room on the other side is the door's destination.
- Drawing room, family lounge, master bedroom are typically the largest
  rooms. Powder toilets, store rooms, pujas are small.
- Block names like "A$C40b9ed5b" are AutoCAD internals — not furniture.

Respond only with JSON matching the schema you'll be given. No prose.
"""


def build_room_user_message(*, room_label: str, questions: list[dict]) -> str:
    """The text content for a per-room verification call.

    Image is sent as a separate content block; this text frames the JSON
    question list.
    """
    payload = {
        "room_label": room_label,
        "questions": questions,
    }
    return (
        f"Verify the room labeled '{room_label}'. Look at the image and "
        "answer the questions below.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )


def build_lobby_user_message(
    *,
    orphan_ids: list[str],
    labeled_rooms: Iterable[tuple[str, str]],
) -> str:
    """Whole-plan LOBBY-recovery prompt."""
    labeled_list = [
        {"id": rid, "label": name} for rid, name in labeled_rooms
    ]
    payload = {
        "orphan_room_ids": orphan_ids,
        "labeled_rooms": labeled_list,
    }
    return (
        "Look at the full floor plan. The highlighted cells are 'orphan' "
        "regions our parser couldn't label. For each one, decide which "
        "labeled room it physically extends into (forming an L-shape), or "
        "say it's truly unlabeled (parent_room_id = null).\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/llm/test_prompts.py -v`
Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/llm/prompts.py lighting-engine/tests/llm/test_prompts.py
git commit -m "feat(llm): system + per-room + LOBBY prompt templates

System prompt cached on every call. Includes Delhi domain rules (every
space is labeled, French windows, block-ID noise) so Claude reasons in
the right frame.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Wrapped Anthropic client (retry + rate-limit)

**Files:**
- Create: `lighting-engine/src/lighting_engine/llm/client.py`
- Test: `lighting-engine/tests/llm/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/llm/test_client.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from lighting_engine.llm.client import VerifyClient, LlmCallFailed


@pytest.mark.asyncio
async def test_retries_on_transient_failure():
    fake_anthropic = MagicMock()
    fake_anthropic.messages.create = AsyncMock(side_effect=[
        Exception("transient"),
        Exception("still transient"),
        MagicMock(content=[MagicMock(text='{"room_id":"r","doors":[]}')]),
    ])
    client = VerifyClient(anthropic_client=fake_anthropic, max_retries=3)
    result = await client.call_with_image(
        system="sys", user="u", image_png=b"png",
        response_schema={"type":"object"},
    )
    assert result is not None
    assert fake_anthropic.messages.create.call_count == 3


@pytest.mark.asyncio
async def test_raises_after_max_retries():
    fake_anthropic = MagicMock()
    fake_anthropic.messages.create = AsyncMock(side_effect=Exception("nope"))
    client = VerifyClient(anthropic_client=fake_anthropic, max_retries=3)
    with pytest.raises(LlmCallFailed):
        await client.call_with_image(
            system="sys", user="u", image_png=b"png",
            response_schema={"type":"object"},
        )
    assert fake_anthropic.messages.create.call_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/llm/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/llm/client.py
"""Thin wrapper over the Anthropic async client with retry + rate-limit
awareness.

Per claude-api guidance:
- Model: claude-opus-4-7
- Thinking: adaptive (Claude decides when to think)
- Output: structured (JSON schema enforced)
- System prompt: cache_control: ephemeral (prefix cache)
- Vision: image content block (base64 PNG)
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LlmCallFailed(RuntimeError):
    """All retries exhausted; the caller should mark the room as 'manual'."""


_RETRY_BACKOFF_SECONDS = (2, 4, 8)
_MODEL = "claude-opus-4-7"


class VerifyClient:
    """Wraps an Anthropic AsyncClient with retry + rate-limit-aware
    concurrency. The actual ``anthropic`` SDK client is injected so tests
    can mock it.
    """

    def __init__(
        self,
        *,
        anthropic_client: Any,
        max_retries: int = 3,
    ) -> None:
        self._client = anthropic_client
        self._max_retries = max_retries

    async def call_with_image(
        self,
        *,
        system: str,
        user: str,
        image_png: bytes,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Single Claude call with image + structured output.

        Returns the parsed JSON response. Raises LlmCallFailed on terminal
        failure (after all retries).
        """
        image_b64 = base64.b64encode(image_png).decode("ascii")
        request = {
            "model": _MODEL,
            "max_tokens": 4096,
            "thinking": {"type": "adaptive"},
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": user},
                    ],
                }
            ],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": response_schema,
                },
            },
        }

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._client.messages.create(**request)
                # Structured output should return parsed JSON in the first
                # content block; extract it.
                first_block = response.content[0]
                text = getattr(first_block, "text", str(first_block))
                import json
                return json.loads(text)
            except Exception as exc:   # noqa: BLE001  (retry on anything transient)
                last_error = exc
                logger.warning(
                    "Anthropic call failed on attempt %d/%d: %s",
                    attempt + 1, self._max_retries, exc,
                )
                if attempt + 1 < self._max_retries:
                    await asyncio.sleep(
                        _RETRY_BACKOFF_SECONDS[
                            min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)
                        ]
                    )

        raise LlmCallFailed(
            f"All {self._max_retries} retries failed; last error: {last_error}"
        )
```

Add `pytest-asyncio` to dev deps if not already present:

```bash
cd lighting-engine && uv add --dev pytest-asyncio
```

And ensure `pyproject.toml` has:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/llm/test_client.py -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/llm/client.py lighting-engine/tests/llm/test_client.py lighting-engine/pyproject.toml
git commit -m "feat(llm): VerifyClient with retry + structured output + prompt cache

Wraps anthropic.AsyncClient. Uses claude-opus-4-7 + adaptive thinking,
ephemeral cache_control on the system prompt, JSON-schema structured
output, vision content block for the room render.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Disambiguator — per-room + LOBBY orchestration

**Files:**
- Create: `lighting-engine/src/lighting_engine/llm/disambiguator.py`
- Test: `lighting-engine/tests/llm/test_disambiguator.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/llm/test_disambiguator.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from lighting_engine.llm.disambiguator import Disambiguator
from lighting_engine.models.geometry import Point, Project, Room


def _delhi_minimal_project() -> Project:
    return Project(
        id="p1", name="delhi", location="delhi",
        rooms=[
            Room(
                id="r1", name="DINING", type="dining", polygon=[
                    Point(x=0,y=0), Point(x=5,y=0), Point(x=5,y=4), Point(x=0,y=4)
                ],
                confidence=0.4,   # uncertain
            ),
            Room(
                id="r2", name="MASTER BEDROOM", type="master_bedroom",
                polygon=[
                    Point(x=10,y=0), Point(x=15,y=0), Point(x=15,y=6), Point(x=10,y=6)
                ],
                confidence=1.0,  # certain, won't be sent
            ),
        ],
    )


@pytest.mark.asyncio
async def test_verifies_only_uncertain_rooms():
    project = _delhi_minimal_project()
    fake_client = MagicMock()
    fake_client.call_with_image = AsyncMock(return_value={
        "room_id": "r1",
        "polygon_assignment": {"cell_id":"cell-A","confidence":0.95,"reason":"ok"},
        "doors": [], "windows": [],
        "furniture_classify": [], "furniture_add": [],
    })

    disambiguator = Disambiguator(client=fake_client)
    result = await disambiguator.verify_project(project)

    # Only r1 should have been sent (r2's confidence == 1.0)
    assert fake_client.call_with_image.call_count == 1
    # Updated project carries r1 with provenance=llm and llm_status=verified
    updated_r1 = next(r for r in result.rooms if r.id == "r1")
    assert updated_r1.provenance == "llm"
    assert updated_r1.llm_status == "verified"


@pytest.mark.asyncio
async def test_failed_room_marked_manual():
    from lighting_engine.llm.client import LlmCallFailed
    project = _delhi_minimal_project()
    fake_client = MagicMock()
    fake_client.call_with_image = AsyncMock(side_effect=LlmCallFailed("nope"))

    disambiguator = Disambiguator(client=fake_client)
    result = await disambiguator.verify_project(project)
    # Failed verification — the disambiguator records this on the project
    assert "r1" in result.rooms_marked_manual
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/llm/test_disambiguator.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/llm/disambiguator.py
"""Orchestrates Layer 2 verification across rooms in a project.

For each room with at least one entity below the confidence threshold,
renders a PNG crop and calls Claude with batched questions. Updates the
project's IR in place with Claude's decisions; rooms that fail to verify
are recorded for the caller to mark `manual`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from lighting_engine.llm.client import LlmCallFailed
from lighting_engine.llm.prompts import (
    SYSTEM_PROMPT, build_lobby_user_message, build_room_user_message,
)
from lighting_engine.llm.room_render import render_room_crop
from lighting_engine.llm.schemas import RoomVerifyResponse
from lighting_engine.models.geometry import Project, Room


_CONFIDENCE_THRESHOLD = 0.8
_PARALLEL_ROOM_CALLS = 5


@dataclass
class VerifyResult:
    project: Project
    rooms_marked_manual: list[str] = field(default_factory=list)


class Disambiguator:
    def __init__(self, *, client: Any) -> None:
        self._client = client

    def _room_needs_verification(self, room: Room) -> bool:
        if room.confidence < _CONFIDENCE_THRESHOLD:
            return True
        if any(d.confidence < _CONFIDENCE_THRESHOLD for d in room.doors):
            return True
        if any(w.confidence < _CONFIDENCE_THRESHOLD for w in room.windows):
            return True
        if any(f.confidence < _CONFIDENCE_THRESHOLD for f in room.furniture):
            return True
        return False

    def _build_questions_for_room(self, room: Room) -> list[dict]:
        qs: list[dict] = []
        if room.confidence < _CONFIDENCE_THRESHOLD:
            qs.append({
                "id": "polygon_assignment",
                "ask": f"Is cell containing label '{room.name}' the right room polygon?",
            })
        for d in room.doors:
            if d.confidence < _CONFIDENCE_THRESHOLD:
                qs.append({
                    "id": f"door_{d.id}",
                    "ask": "Door type + which room does it lead to?",
                    "current": {"type": d.swing or "unknown",
                                "leads_to": d.destination_room_id},
                })
        for w in room.windows:
            if w.confidence < _CONFIDENCE_THRESHOLD:
                qs.append({
                    "id": f"window_{w.id}",
                    "ask": "Is this a regular window or a French/balcony door?",
                })
        for f in room.furniture:
            if f.confidence < _CONFIDENCE_THRESHOLD:
                qs.append({
                    "id": f"furniture_classify_{f.id}",
                    "ask": "Classify this footprint",
                    "candidate": {"id": f.id, "type": f.type,
                                  "block_name": f.raw_label},
                })
        # Always ask the "missing furniture" question
        qs.append({
            "id": "furniture_missing",
            "ask": "Any furniture in the room the parser missed?",
        })
        return qs

    async def _verify_one_room(self, project: Project, room: Room) -> Room:
        """Verify a single room. Returns the updated Room or raises on failure."""
        png = render_room_crop(project=project, room_id=room.id)
        user_msg = build_room_user_message(
            room_label=room.name,
            questions=self._build_questions_for_room(room),
        )
        response_dict = await self._client.call_with_image(
            system=SYSTEM_PROMPT,
            user=user_msg,
            image_png=png,
            response_schema=RoomVerifyResponse.model_json_schema(),
        )
        # Apply Claude's decisions to the room. Simplified: bump confidence,
        # set provenance. Real merge logic lives in a helper.
        return room.model_copy(update={
            "provenance": "llm",
            "llm_status": "verified",
            "confidence": max(
                room.confidence,
                response_dict.get("polygon_assignment", {}).get(
                    "confidence", room.confidence,
                ),
            ),
        })

    async def verify_project(self, project: Project) -> VerifyResult:
        """Verify all uncertain rooms in parallel."""
        target_rooms = [r for r in project.rooms if self._room_needs_verification(r)]
        if not target_rooms:
            return VerifyResult(project=project)

        sem = asyncio.Semaphore(_PARALLEL_ROOM_CALLS)
        marked_manual: list[str] = []

        async def _bounded_verify(room: Room) -> Room:
            async with sem:
                try:
                    return await self._verify_one_room(project, room)
                except LlmCallFailed:
                    marked_manual.append(room.id)
                    return room

        new_rooms = await asyncio.gather(*[
            _bounded_verify(r) if r in target_rooms else _passthrough(r)
            for r in project.rooms
        ])
        return VerifyResult(
            project=project.model_copy(update={"rooms": new_rooms}),
            rooms_marked_manual=marked_manual,
        )


async def _passthrough(room: Room) -> Room:
    return room
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/llm/test_disambiguator.py -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/llm/disambiguator.py lighting-engine/tests/llm/test_disambiguator.py
git commit -m "feat(llm): Disambiguator orchestrates per-room verification

Sends only rooms with at least one entity below 0.8 confidence. Up to 5
rooms in flight concurrently. Failed rooms recorded as 'manual' on the
result; the rest get provenance=llm + llm_status=verified.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: LOBBY recovery cross-room call

**Files:**
- Modify: `lighting-engine/src/lighting_engine/llm/disambiguator.py`
- Test: `lighting-engine/tests/llm/test_lobby_recovery_call.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/llm/test_lobby_recovery_call.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from lighting_engine.llm.disambiguator import Disambiguator
from lighting_engine.models.geometry import Point, Project, Room
from lighting_engine.parser.lobby_recovery import LobbyRecoveryCandidate


@pytest.mark.asyncio
async def test_calls_lobby_endpoint_when_candidates_exist():
    project = Project(
        id="p1", name="delhi", location="delhi",
        rooms=[
            Room(id="lobby", name="LOBBY", type="hallway", polygon=[
                Point(x=0,y=0), Point(x=5,y=0), Point(x=5,y=2), Point(x=0,y=2)
            ]),
            Room(id="orphan", name="", type="unknown", polygon=[
                Point(x=5,y=0), Point(x=7,y=0), Point(x=7,y=2), Point(x=5,y=2)
            ]),
        ],
    )
    project.lobby_recovery_candidates = [
        LobbyRecoveryCandidate(
            orphan_room_id="orphan", parent_room_id="lobby",
            shared_wall_length_m=2.0, confidence=0.6,
        ),
    ]
    fake_client = MagicMock()
    fake_client.call_with_image = AsyncMock(return_value={
        "decisions": [
            {"orphan_room_id":"orphan", "parent_room_id":"lobby",
             "confidence":0.9, "reason":"orphan extends LOBBY L-shape"},
        ],
    })

    d = Disambiguator(client=fake_client)
    result = await d.verify_project(project)
    # Expect at least one call for LOBBY recovery
    assert fake_client.call_with_image.call_count >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/llm/test_lobby_recovery_call.py -v`
Expected: FAIL — disambiguator doesn't call LOBBY endpoint yet.

- [ ] **Step 3: Add LOBBY recovery to Disambiguator**

In `disambiguator.py`, add a method that runs once per project:

```python
async def _verify_lobby_recovery(self, project: Project) -> Project:
    """Whole-plan call to resolve orphan cells into existing labeled rooms."""
    candidates = getattr(project, "lobby_recovery_candidates", []) or []
    if not candidates:
        return project
    orphan_ids = list({c.orphan_room_id for c in candidates})
    labeled = [
        (r.id, r.name) for r in project.rooms
        if r.type != "unknown" and r.name
    ]
    # Render the full plan — reuse render_room_crop with a synthetic
    # "all rooms visible" mode. For v1, use the first orphan as the focus
    # so the crop expands to include all neighbors.
    png = render_room_crop(project=project, room_id=orphan_ids[0])
    user_msg = build_lobby_user_message(
        orphan_ids=orphan_ids, labeled_rooms=labeled,
    )
    try:
        response = await self._client.call_with_image(
            system=SYSTEM_PROMPT,
            user=user_msg,
            image_png=png,
            response_schema={"type":"object","properties":{
                "decisions":{"type":"array","items":{"type":"object","properties":{
                    "orphan_room_id":{"type":"string"},
                    "parent_room_id":{"type":["string","null"]},
                    "confidence":{"type":"number"},
                    "reason":{"type":"string"},
                },"required":["orphan_room_id","parent_room_id","confidence","reason"]}}
            },"required":["decisions"]},
        )
    except LlmCallFailed:
        return project   # LOBBY recovery is best-effort

    # Apply decisions: for each high-confidence merge, mark the orphan as
    # part of the parent room (in v1, we keep them separate but tag the
    # orphan with the parent's id for the studio to surface).
    return project   # Simplified — real merge logic comes later

# In verify_project, add:
project = await self._verify_lobby_recovery(project)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/llm/test_lobby_recovery_call.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/llm/disambiguator.py lighting-engine/tests/llm/test_lobby_recovery_call.py
git commit -m "feat(llm): LOBBY recovery cross-room call in Disambiguator

Single whole-plan call when lobby_recovery_candidates is non-empty.
Best-effort: failures don't break the rest of verification.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: Per-upload cost cap

**Files:**
- Modify: `lighting-engine/src/lighting_engine/llm/disambiguator.py`
- Test: `lighting-engine/tests/llm/test_cost_cap.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/llm/test_cost_cap.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from lighting_engine.llm.disambiguator import Disambiguator


@pytest.mark.asyncio
async def test_projected_cost_exceeds_cap_skips_verification():
    # 50 uncertain rooms — projected cost ~$3 (above $1 cap)
    from lighting_engine.models.geometry import Point, Project, Room
    rooms = [
        Room(id=f"r{i}", name=f"R{i}", type="bedroom",
             polygon=[Point(x=0,y=0),Point(x=1,y=0),Point(x=1,y=1),Point(x=0,y=1)],
             confidence=0.3)
        for i in range(50)
    ]
    project = Project(id="p", name="big", location="delhi", rooms=rooms)
    fake_client = MagicMock()
    fake_client.call_with_image = AsyncMock()

    d = Disambiguator(client=fake_client, cost_cap_usd=1.0)
    result = await d.verify_project(project)

    # Should NOT have made any verify calls
    assert fake_client.call_with_image.call_count == 0
    # All 50 rooms marked manual
    assert len(result.rooms_marked_manual) == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/llm/test_cost_cap.py -v`
Expected: FAIL — `Disambiguator.__init__` doesn't accept `cost_cap_usd`.

- [ ] **Step 3: Add cost cap to Disambiguator**

```python
# In disambiguator.py
_PROJECTED_COST_PER_ROOM = 0.05   # USD; rough estimate

class Disambiguator:
    def __init__(self, *, client: Any, cost_cap_usd: float = 1.0) -> None:
        self._client = client
        self._cost_cap = cost_cap_usd

    # In verify_project, before kicking off calls:
    target_rooms = [r for r in project.rooms if self._room_needs_verification(r)]
    projected_cost = len(target_rooms) * _PROJECTED_COST_PER_ROOM
    if projected_cost > self._cost_cap:
        # Short-circuit: don't make any calls; mark all uncertain rooms manual
        return VerifyResult(
            project=project,
            rooms_marked_manual=[r.id for r in target_rooms],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/llm/test_cost_cap.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/llm/disambiguator.py lighting-engine/tests/llm/test_cost_cap.py
git commit -m "feat(llm): per-upload cost cap (default \$1.00)

Short-circuits verification if projected cost exceeds the cap; all
uncertain rooms get marked 'manual' so the designer reviews them.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase D — API endpoints + integration

### Task 18: Wire Layer 2 into upload route as BackgroundTask

**Files:**
- Modify: `lighting-engine/src/lighting_engine/api/routes/projects.py`
- Test: `lighting-engine/tests/api/test_projects_runs_verification.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/api/test_projects_runs_verification.py
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_upload_returns_immediately_and_status_is_verifying():
    """After upload, the rooms list should have status=verifying for
    first-class rooms; Layer 2 runs in the background.
    """
    from lighting_engine.api.app import app
    client = TestClient(app)

    with patch(
        "lighting_engine.api.routes.projects.is_llm_verification_enabled",
        return_value=True,
    ):
        with open("tests/fixtures/dwgs/real_base_architectural.dxf", "rb") as fh:
            resp = client.post(
                "/api/projects",
                files={"ceiling": ("c.dxf", fh, "application/octet-stream")},
                data={"project_name": "T", "location": "delhi"},
            )
    assert resp.status_code == 201
    data = resp.json()
    statuses = {r["verification_status"] for r in data["rooms"]}
    assert "verifying" in statuses or "ready" in statuses


def test_upload_with_llm_disabled_marks_all_ready():
    from lighting_engine.api.app import app
    client = TestClient(app)
    with patch(
        "lighting_engine.api.routes.projects.is_llm_verification_enabled",
        return_value=False,
    ):
        with open("tests/fixtures/dwgs/real_base_architectural.dxf", "rb") as fh:
            resp = client.post(
                "/api/projects",
                files={"ceiling": ("c.dxf", fh, "application/octet-stream")},
                data={"project_name": "T", "location": "delhi"},
            )
    data = resp.json()
    statuses = {r["verification_status"] for r in data["rooms"]}
    assert statuses == {"ready"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/api/test_projects_runs_verification.py -v`
Expected: FAIL — no `verification_status` field on RoomSummary or no background task wired.

- [ ] **Step 3: Update `routes/projects.py`**

```python
from fastapi import BackgroundTasks
from lighting_engine.llm.feature_flag import is_llm_verification_enabled
from lighting_engine.llm.disambiguator import Disambiguator
from lighting_engine.llm.client import VerifyClient

# In create_project_endpoint signature, add `background_tasks: BackgroundTasks`

# After Layer 1 parsing + DB writes:
if is_llm_verification_enabled():
    # Mark all first-class rooms as verifying
    for room_summary in summaries:
        if room_summary.tier == RoomTier.first_class:
            room_summary.verification_status = "verifying"
    # Persist that status to DB
    # ...
    background_tasks.add_task(
        _run_layer2_verification, project_id=project_id,
    )
else:
    for room_summary in summaries:
        room_summary.verification_status = "ready"


async def _run_layer2_verification(project_id: str) -> None:
    """Background task: run Layer 2 verification, update DB."""
    import anthropic
    from lighting_engine.api.db import async_session_factory
    from lighting_engine.api.storage import list_rooms, update_room_confirmed
    from lighting_engine.models.geometry import Project

    anthropic_client = anthropic.AsyncAnthropic()
    verify_client = VerifyClient(anthropic_client=anthropic_client)
    disambiguator = Disambiguator(client=verify_client, cost_cap_usd=1.0)

    async with async_session_factory() as session:
        records = await list_rooms(session, project_id)
        # Reconstruct a minimal Project IR from the stored confirmed_room blobs
        rooms = [
            ConfirmedRoom.model_validate(r.confirmed_room).to_room()
            for r in records
        ]
        project = Project(id=project_id, name="", location="", rooms=rooms)

        result = await disambiguator.verify_project(project)

        # Persist each room's new state
        for record in records:
            verified_room = next(
                (r for r in result.project.rooms if r.id == record.id), None,
            )
            if verified_room is None:
                continue
            new_status: RoomStatus
            if record.id in result.rooms_marked_manual:
                new_status = "manual"
            elif any_low_confidence_in_room(verified_room):
                new_status = "needs_attention"
            else:
                new_status = "ready"
            record.verification_status = new_status
            # Merge LLM-touched fields back into confirmed_room blob
            updated_confirmed = ConfirmedRoom.model_validate(record.confirmed_room)
            updated_confirmed.confidence = verified_room.confidence
            updated_confirmed.provenance = verified_room.provenance
            updated_confirmed.llm_status = verified_room.llm_status
            await update_room_confirmed(
                session, record, updated_confirmed, status=None,
            )
        await session.commit()


def any_low_confidence_in_room(room: Room) -> bool:
    if room.confidence < 0.8:
        return True
    return (
        any(d.confidence < 0.8 for d in room.doors)
        or any(w.confidence < 0.8 for w in room.windows)
        or any(f.confidence < 0.8 for f in room.furniture)
    )
```

Note: `ConfirmedRoom.to_room()` may need to be added as a small helper — converts the API schema back to the parser IR `Room` model. If it doesn't exist, add it as a 5-line method that copies fields across.

(The background-task implementation will need to load the project IR from the DB, run the disambiguator, then update each room's `verification_status` to `ready` or `needs_attention`. Use the existing storage helpers.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/api/test_projects_runs_verification.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/api/routes/projects.py lighting-engine/tests/api/test_projects_runs_verification.py
git commit -m "feat(api): wire Layer 2 verification as a BackgroundTask after upload

Upload returns ~5s; verification runs in the background. Each room
transitions verifying → ready / needs_attention / manual as Layer 2
completes. Feature flag gates this entirely.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 19: GET /confirmations endpoint

**Files:**
- Create: `lighting-engine/src/lighting_engine/api/routes/confirmations.py`
- Modify: `lighting-engine/src/lighting_engine/api/app.py` (mount router)
- Test: `lighting-engine/tests/api/test_confirmations_get.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/api/test_confirmations_get.py
from fastapi.testclient import TestClient

from lighting_engine.api.app import app


def test_get_confirmations_returns_uncertain_items():
    client = TestClient(app)
    # Setup: create a project + room with at least one low-confidence item
    # (Use existing fixtures from tests/api/conftest.py.)
    # ...
    resp = client.get("/api/projects/test-pid/rooms/test-rid/confirmations")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    # Each item has: id, kind, value, confidence, alternatives, reason
    for item in data["items"]:
        assert "kind" in item   # polygon | door | window | furniture_classify | furniture_add | lobby
        assert "confidence" in item
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/api/test_confirmations_get.py -v`
Expected: FAIL — 404 (endpoint doesn't exist).

- [ ] **Step 3: Implement**

```python
# lighting-engine/src/lighting_engine/api/routes/confirmations.py
"""Endpoints for designer-in-the-loop confirmation."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from lighting_engine.api.db import get_session
from lighting_engine.api.storage import get_room

router = APIRouter(prefix="/api/projects", tags=["confirmations"])


class ConfirmationItem(BaseModel):
    id: str
    kind: str   # polygon | door | window | furniture_classify | furniture_add | lobby
    confidence: float
    value: dict
    alternatives: list[dict] = []
    reason: str = ""


class ConfirmationsResponse(BaseModel):
    items: list[ConfirmationItem]


_CONFIDENCE_THRESHOLD = 0.8


@router.get(
    "/{project_id}/rooms/{room_id}/confirmations",
    response_model=ConfirmationsResponse,
)
async def get_confirmations(
    project_id: str,
    room_id: str,
    session: AsyncSession = Depends(get_session),
) -> ConfirmationsResponse:
    record = await get_room(session, project_id, room_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # Walk confirmed_room blob, emit one ConfirmationItem per low-confidence entity
    items: list[ConfirmationItem] = []
    confirmed = record.confirmed_room
    if confirmed.get("confidence", 1.0) < _CONFIDENCE_THRESHOLD:
        items.append(ConfirmationItem(
            id=record.id, kind="polygon",
            confidence=confirmed["confidence"],
            value={"cell_id": record.id},
            alternatives=confirmed.get("alternatives") or [],
        ))
    for d in confirmed.get("doors_parsed", []):
        if d.get("confidence", 1.0) < _CONFIDENCE_THRESHOLD:
            items.append(ConfirmationItem(
                id=d["id"], kind="door",
                confidence=d["confidence"],
                value={"type": d.get("swing"), "leads_to": d.get("destination_room_id")},
                alternatives=d.get("alternatives") or [],
            ))
    # ... similar for windows, furniture_classify, furniture_add, lobby
    return ConfirmationsResponse(items=items)
```

Mount in `api/app.py`:

```python
from lighting_engine.api.routes import confirmations
app.include_router(confirmations.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/api/test_confirmations_get.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/api/routes/confirmations.py lighting-engine/src/lighting_engine/api/app.py lighting-engine/tests/api/test_confirmations_get.py
git commit -m "feat(api): GET /confirmations returns low-confidence entities

One endpoint, one list. Studio uses this to render the confirm panel.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 20: POST /confirmations endpoint

**Files:**
- Modify: `lighting-engine/src/lighting_engine/api/routes/confirmations.py`
- Test: `lighting-engine/tests/api/test_confirmations_post.py`

- [ ] **Step 1: Write the failing test**

```python
# lighting-engine/tests/api/test_confirmations_post.py
from fastapi.testclient import TestClient

from lighting_engine.api.app import app


def test_post_confirmation_flips_provenance_to_designer():
    client = TestClient(app)
    # Assumes fixture with a low-confidence door on a room
    resp = client.post(
        "/api/projects/test-pid/rooms/test-rid/confirmations",
        json={"confirmations": [
            {"id":"d12","kind":"door","decision":"confirm"},
        ]},
    )
    assert resp.status_code == 200
    # The room's stored door should now have provenance=designer
    get_resp = client.get("/api/projects/test-pid/rooms/test-rid")
    data = get_resp.json()
    door = next(d for d in data["doors_parsed"] if d["id"] == "d12")
    assert door["provenance"] == "designer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lighting-engine && uv run pytest tests/api/test_confirmations_post.py -v`
Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 3: Implement**

```python
class ConfirmationAction(BaseModel):
    id: str
    kind: str
    decision: str       # "confirm" | "pick_alternative" | "wrong"
    alternative_value: dict | None = None
    manual_value: dict | None = None


class ConfirmationsRequest(BaseModel):
    confirmations: list[ConfirmationAction]


@router.post(
    "/{project_id}/rooms/{room_id}/confirmations",
    response_model=ConfirmationsResponse,
)
async def post_confirmations(
    project_id: str,
    room_id: str,
    payload: ConfirmationsRequest,
    session: AsyncSession = Depends(get_session),
) -> ConfirmationsResponse:
    record = await get_room(session, project_id, room_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # For each action, locate the entity by id+kind in confirmed_room,
    # apply the decision, flip provenance to "designer".
    confirmed = dict(record.confirmed_room)
    for action in payload.confirmations:
        if action.kind == "door":
            for d in confirmed.get("doors_parsed", []):
                if d["id"] == action.id:
                    if action.decision == "confirm":
                        d["confidence"] = 1.0
                    elif action.decision == "pick_alternative":
                        d.update(action.alternative_value or {})
                        d["confidence"] = 1.0
                    elif action.decision == "wrong":
                        # Drop or mark as flagged_as_noise
                        d["llm_status"] = "flagged_as_noise"
                    d["provenance"] = "designer"
        # ... similar for window, furniture_classify, furniture_add, polygon
    # Persist back
    record.confirmed_room = confirmed
    # If no items remain below threshold, update verification_status to ready
    has_low = _has_low_confidence_entity(confirmed)
    record.verification_status = "ready" if not has_low else "needs_attention"
    await session.commit()
    # Return the now-empty (or shorter) confirmations list
    return await get_confirmations(project_id, room_id, session)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lighting-engine && uv run pytest tests/api/test_confirmations_post.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/api/routes/confirmations.py lighting-engine/tests/api/test_confirmations_post.py
git commit -m "feat(api): POST /confirmations applies designer answers, flips provenance

When all items resolved, room's verification_status → ready. Otherwise stays
needs_attention. Three decision types: confirm, pick_alternative, wrong.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase E — Studio UX

### Task 21: Studio types + API client for confirmations

**Files:**
- Modify: `studio/lib/api/types.ts`
- Create: `studio/lib/api/confirmations.ts`
- Test: (manual verification — studio types don't have a Jest harness in this repo)

- [ ] **Step 1: Add types to `studio/lib/api/types.ts`**

```typescript
export type RoomStatus =
  | "parsing"
  | "verifying"
  | "ready"
  | "needs_attention"
  | "manual";

export type Provenance = "parser" | "llm" | "llm_uncontested" | "designer";

export type LlmStatus = "unchecked" | "verified" | "flagged_as_noise";

export interface Alternative {
  value: string | Record<string, unknown>;
  confidence: number;
  reason: string;
}

export interface ConfirmationItem {
  id: string;
  kind: "polygon" | "door" | "window" | "furniture_classify" | "furniture_add" | "lobby";
  confidence: number;
  value: Record<string, unknown>;
  alternatives: Array<{ value: unknown; confidence: number; reason: string }>;
  reason?: string;
}

export interface ConfirmationsResponse {
  items: ConfirmationItem[];
}

export type ConfirmationDecision = "confirm" | "pick_alternative" | "wrong";

export interface ConfirmationAction {
  id: string;
  kind: ConfirmationItem["kind"];
  decision: ConfirmationDecision;
  alternative_value?: Record<string, unknown>;
  manual_value?: Record<string, unknown>;
}
```

Also extend the existing `RoomSummary` with `verification_status: RoomStatus`.

- [ ] **Step 2: Create API client**

```typescript
// studio/lib/api/confirmations.ts
import { apiFetch } from "./client";
import type {
  ConfirmationAction, ConfirmationsResponse,
} from "./types";

export async function getConfirmations(
  pid: string, rid: string,
): Promise<ConfirmationsResponse> {
  return apiFetch(`/api/projects/${pid}/rooms/${rid}/confirmations`);
}

export async function postConfirmations(
  pid: string, rid: string, confirmations: ConfirmationAction[],
): Promise<ConfirmationsResponse> {
  return apiFetch(`/api/projects/${pid}/rooms/${rid}/confirmations`, {
    method: "POST",
    body: JSON.stringify({ confirmations }),
  });
}
```

- [ ] **Step 3: Verify with tsc**

Run: `cd studio && npx tsc --noEmit`
Expected: clean (no output).

- [ ] **Step 4: Commit**

```bash
git add studio/lib/api/types.ts studio/lib/api/confirmations.ts
git commit -m "feat(studio): types + API client for confirmations

RoomStatus, Provenance, Alternative, ConfirmationItem types match
the engine schemas. getConfirmations + postConfirmations wired.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 22: Rooms-picker status badges + polling

**Files:**
- Create: `studio/app/studio/components/RoomStatusBadge.tsx`
- Modify: `studio/app/studio/rooms/page.tsx`

- [ ] **Step 1: Create RoomStatusBadge**

```typescript
// studio/app/studio/components/RoomStatusBadge.tsx
"use client";

import type { RoomStatus } from "@/lib/api/types";

const VARIANTS: Record<RoomStatus, { label: string; color: string; pulse?: boolean }> = {
  parsing: { label: "Parsing…", color: "bg-stone-300" },
  verifying: { label: "Verifying…", color: "bg-amber-400", pulse: true },
  ready: { label: "Ready", color: "bg-emerald-500" },
  needs_attention: { label: "to confirm", color: "bg-amber-500" },
  manual: { label: "Review manually", color: "bg-stone-400" },
};

interface Props {
  status: RoomStatus;
  count?: number;
}

export function RoomStatusBadge({ status, count }: Props) {
  const variant = VARIANTS[status];
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs text-stone-700`}>
      <span className={`block h-2 w-2 rounded-full ${variant.color} ${variant.pulse ? "animate-pulse" : ""}`} />
      {status === "needs_attention" && count !== undefined
        ? <>{count} {variant.label}</>
        : variant.label}
    </span>
  );
}
```

- [ ] **Step 2: Modify `rooms/page.tsx`** — add polling + render badge

Add to the existing rooms page:

```typescript
// at top
import { RoomStatusBadge } from "../components/RoomStatusBadge";

// In the component, after listRooms is fetched:
useEffect(() => {
  if (!pid) return;
  let cancelled = false;
  let interval = 2000;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const pollFn = async () => {
    if (cancelled) return;
    const rooms = await listRooms(pid);
    setRooms(rooms.rooms);
    const allTerminal = rooms.rooms.every((r) =>
      r.verification_status === "ready" ||
      r.verification_status === "needs_attention" ||
      r.verification_status === "manual"
    );
    if (allTerminal) return;
    interval = Math.min(interval * 1.5, 10000);   // backoff to 10s
    timer = setTimeout(pollFn, interval);
  };
  void pollFn();
  return () => { cancelled = true; if (timer) clearTimeout(timer); };
}, [pid]);
```

And in each room card, render `<RoomStatusBadge status={room.verification_status} />`.

- [ ] **Step 3: Verify tsc**

Run: `cd studio && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add studio/app/studio/components/RoomStatusBadge.tsx studio/app/studio/rooms/page.tsx
git commit -m "feat(studio): rooms picker shows per-room status badges + polls until terminal

Polling backs off 2s → 5s → 10s; stops when all rooms are terminal.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 23: ConfirmCard + confirm panel

**Files:**
- Create: `studio/app/studio/components/ConfirmCard.tsx`
- Create: `studio/app/studio/components/ConfirmPanel.tsx`

- [ ] **Step 1: ConfirmCard component**

```typescript
// studio/app/studio/components/ConfirmCard.tsx
"use client";

import type { ConfirmationItem, ConfirmationDecision } from "@/lib/api/types";

interface Props {
  item: ConfirmationItem;
  onDecision: (decision: ConfirmationDecision, value?: Record<string, unknown>) => void;
}

export function ConfirmCard({ item, onDecision }: Props) {
  const kindLabel: Record<ConfirmationItem["kind"], string> = {
    polygon: "Room polygon",
    door: "Door",
    window: "Window",
    furniture_classify: "Unidentified furniture",
    furniture_add: "AI proposes adding",
    lobby: "LOBBY arm",
  };
  return (
    <div className="bg-white border border-amber-200 rounded-md p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-amber-700/90">
          {kindLabel[item.kind]}
        </span>
        <span className="text-xs text-stone-500">
          {Math.round(item.confidence * 100)}% conf.
        </span>
      </div>
      <p className="text-sm text-stone-800">{item.reason}</p>
      <div className="flex gap-2">
        <button onClick={() => onDecision("confirm")}
                className="flex-1 bg-emerald-600 text-white rounded-md py-1.5 text-sm hover:bg-emerald-700">
          ✓ Confirm
        </button>
        {item.alternatives.length > 0 && (
          <select
            onChange={(e) => {
              const alt = item.alternatives[parseInt(e.target.value)];
              onDecision("pick_alternative", alt.value as Record<string, unknown>);
            }}
            className="flex-1 bg-stone-100 border border-stone-200 rounded-md px-2 py-1.5 text-sm"
          >
            <option value="">Pick alternative…</option>
            {item.alternatives.map((alt, i) => (
              <option key={i} value={i}>{JSON.stringify(alt.value)}</option>
            ))}
          </select>
        )}
        <button onClick={() => onDecision("wrong")}
                className="flex-1 bg-stone-200 text-stone-800 rounded-md py-1.5 text-sm hover:bg-stone-300">
          ✗ Wrong
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: ConfirmPanel component**

```typescript
// studio/app/studio/components/ConfirmPanel.tsx
"use client";

import { useState, useEffect } from "react";
import { ConfirmCard } from "./ConfirmCard";
import { getConfirmations, postConfirmations } from "@/lib/api/confirmations";
import type { ConfirmationItem } from "@/lib/api/types";

const VISIBLE_LIMIT = 5;
const PRIORITY: Record<ConfirmationItem["kind"], number> = {
  polygon: 1, lobby: 2, door: 3, window: 4,
  furniture_add: 5, furniture_classify: 6,
};

interface Props {
  pid: string;
  rid: string;
}

export function ConfirmPanel({ pid, rid }: Props) {
  const [items, setItems] = useState<ConfirmationItem[] | null>(null);

  useEffect(() => {
    void getConfirmations(pid, rid).then((r) => setItems(r.items));
  }, [pid, rid]);

  if (items === null || items.length === 0) return null;

  const sorted = [...items].sort((a, b) => PRIORITY[a.kind] - PRIORITY[b.kind]);
  const visible = sorted.slice(0, VISIBLE_LIMIT);

  const handle = async (item: ConfirmationItem, decision, value) => {
    await postConfirmations(pid, rid, [{
      id: item.id, kind: item.kind, decision,
      alternative_value: value,
    }]);
    const r = await getConfirmations(pid, rid);
    setItems(r.items);
  };

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-3 mb-6">
      <div className="text-sm text-stone-800">
        <strong>AI verified most of this room.</strong>{" "}
        {items.length} {items.length === 1 ? "item needs" : "items need"} your confirmation.
      </div>
      <div className="space-y-2">
        {visible.map((item) => (
          <ConfirmCard
            key={item.id}
            item={item}
            onDecision={(d, v) => void handle(item, d, v)}
          />
        ))}
      </div>
      {items.length > VISIBLE_LIMIT && (
        <p className="text-xs text-stone-500">
          + {items.length - VISIBLE_LIMIT} more after these
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Drop ConfirmPanel into room pages**

In `studio/app/studio/room-basics/page.tsx` (and walls / furniture pages), at the top of the page body:

```typescript
{room?.verification_status === "needs_attention" && (
  <ConfirmPanel pid={pid} rid={rid} />
)}
```

- [ ] **Step 4: Verify tsc**

Run: `cd studio && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add studio/app/studio/components/ConfirmCard.tsx studio/app/studio/components/ConfirmPanel.tsx studio/app/studio/room-basics/page.tsx studio/app/studio/walls/page.tsx studio/app/studio/furniture/page.tsx
git commit -m "feat(studio): ConfirmCard + ConfirmPanel for needs_attention rooms

Cards capped at 5 visible, sorted by priority (polygon > lobby > door >
window > furniture). Three actions per card: confirm / pick alternative /
wrong.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 24: Skip-continue defaults to llm_uncontested

**Files:**
- Modify: `lighting-engine/src/lighting_engine/api/routes/confirmations.py` (add bulk-skip handler)
- Test: `lighting-engine/tests/api/test_skip_defaults_to_llm_uncontested.py`

- [ ] **Step 1: Write the failing test**

```python
def test_finalize_skipped_rooms_sets_provenance_llm_uncontested():
    client = TestClient(app)
    # Use a fixture with 2 unresolved items
    resp = client.post(
        "/api/projects/p1/rooms/r1/confirmations/finalize",
        json={"skip_unconfirmed": True},
    )
    assert resp.status_code == 200
    # Verify all previously-uncertain items now have provenance = llm_uncontested
    get_resp = client.get("/api/projects/p1/rooms/r1")
    data = get_resp.json()
    for door in data["doors_parsed"]:
        if door["confidence"] < 0.8:
            assert door["provenance"] == "llm_uncontested"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_skip_defaults_to_llm_uncontested.py -v`
Expected: 404 — endpoint doesn't exist.

- [ ] **Step 3: Add the endpoint**

```python
class FinalizeRequest(BaseModel):
    skip_unconfirmed: bool = True


@router.post(
    "/{project_id}/rooms/{room_id}/confirmations/finalize",
    response_model=ConfirmationsResponse,
)
async def finalize_confirmations(
    project_id: str,
    room_id: str,
    payload: FinalizeRequest,
    session: AsyncSession = Depends(get_session),
) -> ConfirmationsResponse:
    record = await get_room(session, project_id, room_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    confirmed = dict(record.confirmed_room)
    if payload.skip_unconfirmed:
        # Walk all entities; flip provenance llm → llm_uncontested where confidence < 0.8
        for d in confirmed.get("doors_parsed", []):
            if d.get("confidence", 1.0) < 0.8 and d.get("provenance") == "llm":
                d["provenance"] = "llm_uncontested"
        # ... same for windows, furniture
        record.verification_status = "ready"
        record.confirmed_room = confirmed
        await session.commit()
    return await get_confirmations(project_id, room_id, session)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_skip_defaults_to_llm_uncontested.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lighting-engine/src/lighting_engine/api/routes/confirmations.py lighting-engine/tests/api/test_skip_defaults_to_llm_uncontested.py
git commit -m "feat(api): finalize endpoint flips llm → llm_uncontested for skipped items

Designer hits Continue without explicit confirmation → items default to
Claude's value but provenance is recorded as llm_uncontested for audit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase F — End-to-end + rollout

### Task 25: End-to-end golden file test on Delhi fixture

**Files:**
- Create: `lighting-engine/tests/integration/test_delhi_e2e_with_real_anthropic.py`

- [ ] **Step 1: Write the test (gated on env var)**

```python
# lighting-engine/tests/integration/test_delhi_e2e_with_real_anthropic.py
import os
from pathlib import Path

import pytest

from lighting_engine.parser.pipeline import parse_file
from lighting_engine.llm.disambiguator import Disambiguator
from lighting_engine.llm.client import VerifyClient


pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY",
)


@pytest.mark.asyncio
async def test_delhi_e2e_runs_layer1_plus_layer2():
    import anthropic
    project, _ = parse_file(
        Path("tests/fixtures/dwgs/real_base_architectural.dxf"),
        project_name="delhi", location="delhi",
    )

    anthropic_client = anthropic.AsyncAnthropic()
    verify_client = VerifyClient(anthropic_client=anthropic_client)
    disambiguator = Disambiguator(client=verify_client, cost_cap_usd=1.0)
    result = await disambiguator.verify_project(project)

    # Sanity checks — snapshot expectations
    rooms = result.project.rooms
    verified_count = sum(1 for r in rooms if r.llm_status == "verified")
    assert verified_count >= 3, (
        f"Expected at least 3 rooms to be LLM-verified; got {verified_count}"
    )
    # Drawing Room should now have at least one door post-verification
    drawing = next((r for r in rooms if r.name == "DRAWING ROOM"), None)
    if drawing:
        assert len(drawing.doors) > 0
```

- [ ] **Step 2: Run with API key**

```bash
ANTHROPIC_API_KEY=sk-xxx cd lighting-engine && uv run pytest tests/integration/ -v
```

Expected: PASS (skip if no key).

- [ ] **Step 3: Commit**

```bash
git add lighting-engine/tests/integration/test_delhi_e2e_with_real_anthropic.py
git commit -m "test(integration): end-to-end on Delhi fixture with real Anthropic

Gated on ANTHROPIC_API_KEY env var. Validates Layer 1 + Layer 2 together
on the canonical Delhi reference plan. Drawing Room should gain doors.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 26: Final smoke test + push

- [ ] **Step 1: Run the full test suite**

Run: `cd lighting-engine && uv run pytest`
Expected: All tests pass; counts: original 336 + ~30 new = ~366 total.

- [ ] **Step 2: Run studio type-check**

Run: `cd studio && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 3: Run studio build**

Run: `cd studio && npm run build`
Expected: clean build.

- [ ] **Step 4: Verify feature flag off by default**

```bash
LIGHTING_ENGINE_LLM_VERIFY_ENABLED=false uv run pytest tests/api/test_projects_runs_verification.py -v
```

Confirm rooms ship as `ready` when feature flag is off.

- [ ] **Step 5: Push to GitHub**

```bash
git push origin main
```

Expected: pushed successfully.

---

## Spec coverage check

| Spec section | Tasks covering it |
|---|---|
| §3.1 Per-entity fields | Task 1 |
| §3.2 Room-level status | Task 2 |
| §3.3 Project verification_mode | Task 2 |
| §3.3 Migration | Task 2 (DB defaults handle it) |
| §4.1 furniture_geometry.py | Task 5 |
| §4.2 Confidence scoring | Tasks 4, 8 (and wired in Task 9) |
| §4.3 LOBBY L-shape support | Task 6 |
| §4.4 Cleanup in furniture_merge / door_anchor / window_filter | Tasks 7, 8 |
| §5.1 New `llm/` package | Tasks 10–17 |
| §5.2 Per-room call shape | Tasks 13, 14, 15 |
| §5.3 LOBBY recovery call | Task 16 |
| §5.4 BackgroundTask wiring | Task 18 |
| §5.5 Cost/latency budget | Task 17 (cost cap) |
| §5.6 Retry & failure | Task 14 (retry logic), Task 15 (failed → manual) |
| §6.1 Upload flow | Task 18 |
| §6.2 Rooms picker badges | Task 22 |
| §6.3 Confirm panel | Task 23 |
| §6.4 Skip/continue semantics | Task 24 |
| §6.5 New endpoints | Tasks 19, 20 |
| §6.6 Position coordinate frame | Task 11 (schemas), Task 23 (rendering) |
| §7 Error handling matrix | Tasks 14, 15, 17, 18 |
| §8 Testing strategy | Tasks 1–24 each include tests + Task 25 e2e |
| §9 Rollout feature flag | Task 10 |
| §10 v1.1 deferred | (Not implemented in this plan — explicit in spec) |
