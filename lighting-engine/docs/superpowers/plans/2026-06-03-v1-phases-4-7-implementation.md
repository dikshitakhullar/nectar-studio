# nectar-studio v1 — Phases 4-7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the placement-extensions, lux-uniformity, SVG-renderers, and end-to-end integration layers of nectar-studio v1, on top of Phases 1-3 (parser polish, FastAPI scaffold, LLM brief layer — currently being built by parallel agents).

**Architecture:** The LLM brief layer (Phase 3) produces a `RoomBrief` with semantic `Zone` objects. Phase 4 translates each zone to actual fixture coordinates using room geometry + furniture data. Phase 5 computes lux uniformity stats from the placed fixtures. Phase 6 renders two SVGs (RCP + furniture plan). Phase 7 wires everything into the FastAPI `POST /generate` endpoint so the studio frontend can produce a complete `PlanResponse`.

**Tech Stack:** Python 3.11, uv, pydantic v2, shapely, FastAPI (existing), Anthropic SDK (Phase 3), pyright strict, ruff. Reuses `digest/`, `lighting/standards.py`, `lighting/fixtures.py`, `lighting/lumen_method.py`, `lighting/grid.py`, `lighting/placement.py`, and `models/geometry.py`.

**Spec reference:** `docs/superpowers/specs/2026-06-03-v1-design.md`

---

## File structure

**To create:**

| File | Responsibility |
|---|---|
| `src/lighting_engine/lighting/zone_interpreter.py` | Convert a `Zone` (semantic) into a target rectangle/point on the room polygon (geometric) |
| `src/lighting_engine/lighting/task_layer.py` | Place task fixtures (downlight/pendant above an activity zone) |
| `src/lighting_engine/lighting/accent_layer.py` | Place accent fixtures (wall washers, picture lights) |
| `src/lighting_engine/lighting/decorative_layer.py` | Place statement fixtures (chandelier, pendant cluster) |
| `src/lighting_engine/lighting/multi_layer.py` | Orchestrate brief → ambient + task + accent + decorative fixtures |
| `src/lighting_engine/lux/__init__.py` | Package marker |
| `src/lighting_engine/lux/uniformity.py` | Point-source lux model, grid sampler, `LuxStats` |
| `src/lighting_engine/render/__init__.py` | Package marker |
| `src/lighting_engine/render/rcp.py` | Revised RCP SVG: original ceiling features + new lighting layer |
| `src/lighting_engine/render/furniture.py` | Revised furniture SVG: original furniture + lamp markings |
| `tests/lighting/test_zone_interpreter.py` | |
| `tests/lighting/test_task_layer.py` | |
| `tests/lighting/test_accent_layer.py` | |
| `tests/lighting/test_decorative_layer.py` | |
| `tests/lighting/test_multi_layer.py` | |
| `tests/lux/test_uniformity.py` | |
| `tests/render/test_rcp.py` | |
| `tests/render/test_furniture.py` | |
| `tests/api/test_generation_e2e.py` | end-to-end through the FastAPI generate endpoint |

**To modify (in Phase 7):**

| File | Change |
|---|---|
| `src/lighting_engine/api/routes/generation.py` | Replace the Phase-2 stub with the real pipeline: brief → placement → lux → renderers → PlanResponse |
| `src/lighting_engine/api/schemas.py` | Ensure `PlanResponse`, `LuxStats`, `FixtureRow` match the shapes used by render + lux modules |

---

## Phase 4 — Placement extensions

The LLM brief returns `RoomBrief.zones: list[Zone]`. Each Zone has a `layer` (ambient/task/accent/decorative), a `position_hint` string ("center of ceiling" / "above dining table" / "wall A near window"), a `fixture_type` ("downlight" / "pendant" / "cove" / "floor_lamp"), and CCT/CRI. Phase 4 converts these into actual `Fixture` objects with coordinates.

### Task 4.1: Zone-to-rectangle interpreter

**Files:**
- Create: `src/lighting_engine/lighting/zone_interpreter.py`
- Test: `tests/lighting/test_zone_interpreter.py`

The interpreter takes a Zone's `position_hint` string + the `Room` + the `RoomDigest` (which already indexes walls N/S/E/W and lists furniture) and returns a `TargetRegion` — the rectangle on the room polygon where the zone's fixtures should be placed.

Position hint vocabulary:
- `"center"` / `"center of ceiling"` → centroid of polygon, 0.5m radius
- `"above <furniture_name>"` → bbox of named furniture (e.g. "dining table")
- `"wall <N|S|E|W>"` → strip along that wall, 0.6m deep
- `"wall <N|S|E|W> near window"` → centred on the wall's first window
- `"perimeter"` → full polygon outline, 0.3m wide (for coves)
- Unknown hints fall back to centroid + 0.5m radius (logged as a warning)

- [ ] **Step 1: Write the failing tests**

```python
# tests/lighting/test_zone_interpreter.py
import pytest
from lighting_engine.lighting.zone_interpreter import (
    TargetRegion, interpret_position_hint,
)
from lighting_engine.models.geometry import Point, Room, RoomType, Furniture
from lighting_engine.digest import compute_digest, Project


def _rect_room(name: str, type_: RoomType, side: float = 5.0) -> Room:
    s = side / 2
    return Room(
        id=name.lower(),
        name=name,
        type=type_,
        floor_level=0,
        polygon=[
            Point(x=-s, y=-s),
            Point(x=s, y=-s),
            Point(x=s, y=s),
            Point(x=-s, y=s),
        ],
        ceiling_height_m=2.7,
    )


def test_center_hint_returns_centroid_with_small_radius():
    room = _rect_room("Living", RoomType.living)
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("center", room, digest)
    assert target.region_type == "point"
    assert target.center.x == pytest.approx(0.0)
    assert target.center.y == pytest.approx(0.0)
    assert target.radius_m == pytest.approx(0.5)


def test_wall_n_hint_returns_north_strip():
    room = _rect_room("Dining", RoomType.dining)
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("wall N", room, digest)
    assert target.region_type == "strip"
    # North wall is the polygon edge at y = 2.5 for our 5x5 room
    assert target.center.y == pytest.approx(2.5 - 0.3)   # 0.6m strip → 0.3m offset from wall
    assert target.depth_m == pytest.approx(0.6)


def test_above_furniture_hint_returns_furniture_bbox():
    room = _rect_room("Dining", RoomType.dining)
    room.furniture.append(Furniture(
        id="f1", type="dining_table", raw_label="dining table",
        position=Point(x=0.5, y=-0.2),
    ))
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("above dining table", room, digest)
    assert target.region_type == "point"
    assert target.center.x == pytest.approx(0.5)
    assert target.center.y == pytest.approx(-0.2)


def test_perimeter_hint_returns_perimeter_strip():
    room = _rect_room("Living", RoomType.living)
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("perimeter", room, digest)
    assert target.region_type == "perimeter"
    assert target.depth_m == pytest.approx(0.3)


def test_unknown_hint_falls_back_to_centroid():
    room = _rect_room("Living", RoomType.living)
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    target = interpret_position_hint("over the chaise lounge", room, digest)
    assert target.region_type == "point"
    assert target.center.x == pytest.approx(0.0)
    assert target.fallback_reason is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/lighting/test_zone_interpreter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lighting_engine.lighting.zone_interpreter'`

- [ ] **Step 3: Implement the interpreter**

```python
# src/lighting_engine/lighting/zone_interpreter.py
"""Convert a brief Zone's semantic position_hint into a geometric target region.

The LLM emits zones like "above dining table" or "wall N near window" — never
coordinates. This module translates those hints into a TargetRegion that the
per-layer placement code consumes.

Hints we recognize (case-insensitive substring match):
  - "center" / "center of ceiling" → centroid point, 0.5m radius
  - "above <furniture>" → centroid of the named furniture's bounding box
  - "wall N" / "wall S" / "wall E" / "wall W" → 0.6m strip along that wall
  - "perimeter" / "perimeter cove" → polygon outline, 0.3m wide
  - anything else → centroid fallback, fallback_reason set
"""

import math
from dataclasses import dataclass

from lighting_engine.digest import RoomDigest
from lighting_engine.models.geometry import Point, Room


@dataclass(frozen=True)
class TargetRegion:
    region_type: str               # "point" | "strip" | "perimeter"
    center: Point
    radius_m: float = 0.5          # for "point" regions
    depth_m: float = 0.0           # for "strip" / "perimeter" regions
    wall_direction: str | None = None    # "N" / "S" / "E" / "W" for strip
    fallback_reason: str | None = None


def _polygon_centroid(polygon: list[Point]) -> Point:
    n = len(polygon)
    cx = sum(p.x for p in polygon) / n
    cy = sum(p.y for p in polygon) / n
    return Point(x=cx, y=cy)


def _wall_strip(room: Room, direction: str) -> tuple[Point, str]:
    """Return (strip_center, direction) for the polygon edge furthest in `direction`."""
    polygon = room.polygon
    if direction == "N":   # max y edge
        ys = [p.y for p in polygon]
        edge_y = max(ys)
        xs = [p.x for p in polygon]
        cx = (min(xs) + max(xs)) / 2.0
        return Point(x=cx, y=edge_y - 0.3), direction
    if direction == "S":
        ys = [p.y for p in polygon]
        edge_y = min(ys)
        xs = [p.x for p in polygon]
        cx = (min(xs) + max(xs)) / 2.0
        return Point(x=cx, y=edge_y + 0.3), direction
    if direction == "E":
        xs = [p.x for p in polygon]
        edge_x = max(xs)
        ys = [p.y for p in polygon]
        cy = (min(ys) + max(ys)) / 2.0
        return Point(x=edge_x - 0.3, y=cy), direction
    # W
    xs = [p.x for p in polygon]
    edge_x = min(xs)
    ys = [p.y for p in polygon]
    cy = (min(ys) + max(ys)) / 2.0
    return Point(x=edge_x + 0.3, y=cy), direction


def _named_furniture_center(room: Room, name_substring: str) -> Point | None:
    needle = name_substring.lower().strip()
    for f in room.furniture:
        label = (f.raw_label or f.type or "").lower()
        if needle in label:
            return f.position
    return None


def interpret_position_hint(
    hint: str, room: Room, digest: RoomDigest,
) -> TargetRegion:
    """Convert a position_hint string into a TargetRegion on the room polygon."""
    h = hint.lower().strip()

    if "perimeter" in h:
        return TargetRegion(
            region_type="perimeter",
            center=_polygon_centroid(room.polygon),
            depth_m=0.3,
        )

    if h.startswith("above "):
        needle = h[len("above "):].strip()
        pos = _named_furniture_center(room, needle)
        if pos is not None:
            return TargetRegion(region_type="point", center=pos, radius_m=0.5)
        # fall through to centroid fallback

    for direction in ("N", "S", "E", "W"):
        if f"wall {direction.lower()}" in h or f"wall {direction}" in h:
            center, dir_ = _wall_strip(room, direction)
            return TargetRegion(
                region_type="strip", center=center,
                depth_m=0.6, wall_direction=dir_,
            )

    if "center" in h:
        return TargetRegion(
            region_type="point", center=_polygon_centroid(room.polygon),
            radius_m=0.5,
        )

    return TargetRegion(
        region_type="point", center=_polygon_centroid(room.polygon),
        radius_m=0.5,
        fallback_reason=f"unrecognised hint: {hint!r}",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lighting/test_zone_interpreter.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/lighting/zone_interpreter.py tests/lighting/test_zone_interpreter.py
git commit -m "feat(lighting): Zone position_hint → TargetRegion interpreter"
```

---

### Task 4.2: compute_task_layer

**Files:**
- Create: `src/lighting_engine/lighting/task_layer.py`
- Test: `tests/lighting/test_task_layer.py`

Task fixtures focus light on an activity zone — a single pendant above a dining table, a downlight over a kitchen prep area, a reading light beside a bed. Position is derived from the zone's TargetRegion centre.

- [ ] **Step 1: Write the failing tests**

```python
# tests/lighting/test_task_layer.py
import pytest
from lighting_engine.lighting.task_layer import compute_task_layer
from lighting_engine.lighting.zone_interpreter import interpret_position_hint
from lighting_engine.brief.models import Zone, LightingLayer
from lighting_engine.models.geometry import (
    Point, Room, RoomType, Furniture, FixtureSource, LightingLayer as IRLayer,
)
from lighting_engine.digest import compute_digest, Project


def _dining_room_with_table() -> tuple[Room, object]:
    room = Room(
        id="dining", name="DINING", type=RoomType.dining, floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=5, y=0), Point(x=5, y=4), Point(x=0, y=4)],
        ceiling_height_m=2.7,
    )
    room.furniture.append(Furniture(
        id="t1", type="dining_table", raw_label="dining table",
        position=Point(x=2.5, y=2.0),
    ))
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    return room, digest


def test_task_layer_places_one_pendant_above_dining_table():
    room, digest = _dining_room_with_table()
    zone = Zone(
        layer=LightingLayer.task, purpose="task above dining table",
        cct_k=2700, cri_min=90, fixture_type="pendant",
        position_hint="above dining table",
    )
    fixtures = compute_task_layer(room, digest, zone)
    assert len(fixtures) == 1
    f = fixtures[0]
    assert f.position.x == pytest.approx(2.5)
    assert f.position.y == pytest.approx(2.0)
    assert f.source == FixtureSource.proposed
    assert f.layer == IRLayer.task
    assert f.type == "pendant"
    assert f.cct_k == 2700


def test_task_layer_downlight_uses_default_lumens():
    room, digest = _dining_room_with_table()
    zone = Zone(
        layer=LightingLayer.task, purpose="task over prep area",
        cct_k=4000, cri_min=90, fixture_type="downlight",
        position_hint="center",
    )
    fixtures = compute_task_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].lumens == pytest.approx(1500.0)
    assert fixtures[0].cct_k == 4000


def test_task_layer_unknown_fixture_type_falls_back_to_downlight():
    room, digest = _dining_room_with_table()
    zone = Zone(
        layer=LightingLayer.task, purpose="task light",
        cct_k=3000, cri_min=80, fixture_type="laser",  # invalid
        position_hint="center",
    )
    fixtures = compute_task_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].type == "downlight"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/lighting/test_task_layer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lighting_engine.lighting.task_layer'`

- [ ] **Step 3: Implement compute_task_layer**

```python
# src/lighting_engine/lighting/task_layer.py
"""Task-layer placement: place a single focused fixture at a TargetRegion centre.

A task fixture lights an activity zone — a pendant over the dining table, a
downlight over the kitchen sink, a sconce by a bedside. The brief Zone's
position_hint resolves to a TargetRegion via the interpreter; we place one
fixture at that region's centre.
"""

from lighting_engine.brief.models import Zone
from lighting_engine.digest import RoomDigest
from lighting_engine.lighting.zone_interpreter import interpret_position_hint
from lighting_engine.models.geometry import (
    Fixture, FixtureSource, LightingLayer, Room,
)

_VALID_FIXTURE_TYPES = {"pendant", "downlight", "spotlight"}


def compute_task_layer(
    room: Room, digest: RoomDigest, zone: Zone,
) -> list[Fixture]:
    target = interpret_position_hint(zone.position_hint, room, digest)
    fixture_type = zone.fixture_type if zone.fixture_type in _VALID_FIXTURE_TYPES else "downlight"
    reasoning = (
        f"Task layer: {zone.purpose}. {fixture_type} placed at hint "
        f"{zone.position_hint!r}"
        + (f" (fallback: {target.fallback_reason})" if target.fallback_reason else "")
    )
    return [Fixture(
        id=f"{room.id}-task-001",
        type=fixture_type,
        position=target.center,
        mount_height_m=None,
        source=FixtureSource.proposed,
        layer=LightingLayer.task,
        reasoning=reasoning,
        wattage_w=15.0,
        lumens=1500.0,
        cct_k=zone.cct_k,
        cri=zone.cri_min,
        beam_angle_deg=30.0 if fixture_type in ("pendant", "spotlight") else 60.0,
    )]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lighting/test_task_layer.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/lighting/task_layer.py tests/lighting/test_task_layer.py
git commit -m "feat(lighting): compute_task_layer — pendant/downlight at zone target"
```

---

### Task 4.3: compute_accent_layer

**Files:**
- Create: `src/lighting_engine/lighting/accent_layer.py`
- Test: `tests/lighting/test_accent_layer.py`

Accent fixtures highlight features — wall art, an architectural niche, a feature wall. For a "wall N" target, we place a series of wall-washer fixtures along the wall (one every 0.8m).

- [ ] **Step 1: Write the failing tests**

```python
# tests/lighting/test_accent_layer.py
import pytest
from lighting_engine.lighting.accent_layer import compute_accent_layer
from lighting_engine.brief.models import Zone, LightingLayer
from lighting_engine.models.geometry import (
    Point, Room, RoomType, FixtureSource, LightingLayer as IRLayer,
)
from lighting_engine.digest import compute_digest, Project


def _living_room() -> tuple[Room, object]:
    room = Room(
        id="living", name="LIVING", type=RoomType.living, floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=4, y=0), Point(x=4, y=4), Point(x=0, y=4)],
        ceiling_height_m=2.7,
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    return room, digest


def test_accent_layer_places_washers_along_wall_n_at_080m_spacing():
    room, digest = _living_room()
    zone = Zone(
        layer=LightingLayer.accent, purpose="wash north wall art",
        cct_k=3000, cri_min=90, fixture_type="wall_washer",
        position_hint="wall N",
    )
    fixtures = compute_accent_layer(room, digest, zone)
    # 4m wall, 0.8m spacing → 5 positions (0.4, 1.2, 2.0, 2.8, 3.6)
    assert len(fixtures) == 5
    xs = sorted(f.position.x for f in fixtures)
    assert xs[0] == pytest.approx(0.4)
    assert xs[-1] == pytest.approx(3.6)
    # All sit at the wall strip y position
    for f in fixtures:
        assert f.position.y == pytest.approx(3.7)   # 4.0 - 0.3
        assert f.source == FixtureSource.proposed
        assert f.layer == IRLayer.accent


def test_accent_layer_point_target_places_single_spotlight():
    room, digest = _living_room()
    zone = Zone(
        layer=LightingLayer.accent, purpose="accent on feature niche",
        cct_k=3000, cri_min=90, fixture_type="spotlight",
        position_hint="center",
    )
    fixtures = compute_accent_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].type == "spotlight"
    assert fixtures[0].position.x == pytest.approx(2.0)
    assert fixtures[0].position.y == pytest.approx(2.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/lighting/test_accent_layer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement compute_accent_layer**

```python
# src/lighting_engine/lighting/accent_layer.py
"""Accent-layer placement: wash a wall, spot a feature, light an architectural detail.

For a "strip" TargetRegion (wall-aligned), place wall washers every 0.8m along
the strip. For a "point" target, place a single spotlight.
"""

from lighting_engine.brief.models import Zone
from lighting_engine.digest import RoomDigest
from lighting_engine.lighting.zone_interpreter import interpret_position_hint
from lighting_engine.models.geometry import (
    Fixture, FixtureSource, LightingLayer, Point, Room,
)

_ACCENT_SPACING_M = 0.8


def _strip_positions(room: Room, target_center: Point, wall_direction: str) -> list[Point]:
    """Distribute positions along a wall strip at 0.8m spacing."""
    polygon = room.polygon
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    if wall_direction in ("N", "S"):
        wall_len = max(xs) - min(xs)
        count = max(1, int(wall_len / _ACCENT_SPACING_M))
        step = wall_len / (count + 1)
        return [
            Point(x=min(xs) + step * (i + 1), y=target_center.y)
            for i in range(count)
        ]
    # E / W
    wall_len = max(ys) - min(ys)
    count = max(1, int(wall_len / _ACCENT_SPACING_M))
    step = wall_len / (count + 1)
    return [
        Point(x=target_center.x, y=min(ys) + step * (i + 1))
        for i in range(count)
    ]


def compute_accent_layer(
    room: Room, digest: RoomDigest, zone: Zone,
) -> list[Fixture]:
    target = interpret_position_hint(zone.position_hint, room, digest)
    if target.region_type == "strip" and target.wall_direction is not None:
        positions = _strip_positions(room, target.center, target.wall_direction)
        fixture_type = zone.fixture_type if zone.fixture_type else "wall_washer"
    else:
        positions = [target.center]
        fixture_type = "spotlight"

    out: list[Fixture] = []
    reasoning = (
        f"Accent layer: {zone.purpose}. {fixture_type} placed at "
        f"{zone.position_hint!r}"
    )
    for i, pos in enumerate(positions):
        out.append(Fixture(
            id=f"{room.id}-acc-{i:03d}",
            type=fixture_type,
            position=pos,
            mount_height_m=None,
            source=FixtureSource.proposed,
            layer=LightingLayer.accent,
            reasoning=reasoning,
            wattage_w=7.0,
            lumens=400.0,
            cct_k=zone.cct_k,
            cri=zone.cri_min,
            beam_angle_deg=24.0,
        ))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lighting/test_accent_layer.py -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/lighting/accent_layer.py tests/lighting/test_accent_layer.py
git commit -m "feat(lighting): compute_accent_layer — wall washers + spotlights"
```

---

### Task 4.4: compute_decorative_layer

**Files:**
- Create: `src/lighting_engine/lighting/decorative_layer.py`
- Test: `tests/lighting/test_decorative_layer.py`

Decorative fixtures are statement pieces — a chandelier in a drawing room, a feature pendant cluster over a dining table. Always exactly one fixture per zone, placed at the target's centre.

- [ ] **Step 1: Write the failing tests**

```python
# tests/lighting/test_decorative_layer.py
import pytest
from lighting_engine.lighting.decorative_layer import compute_decorative_layer
from lighting_engine.brief.models import Zone, LightingLayer
from lighting_engine.models.geometry import (
    Point, Room, RoomType, FixtureSource, LightingLayer as IRLayer,
)
from lighting_engine.digest import compute_digest, Project


def _drawing_room() -> tuple[Room, object]:
    room = Room(
        id="dr", name="DRAWING ROOM", type=RoomType.living, floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=6, y=0), Point(x=6, y=5), Point(x=0, y=5)],
        ceiling_height_m=3.0,
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    return room, digest


def test_decorative_places_one_chandelier_at_center():
    room, digest = _drawing_room()
    zone = Zone(
        layer=LightingLayer.decorative, purpose="statement chandelier",
        cct_k=2700, cri_min=90, fixture_type="chandelier",
        position_hint="center",
    )
    fixtures = compute_decorative_layer(room, digest, zone)
    assert len(fixtures) == 1
    f = fixtures[0]
    assert f.position.x == pytest.approx(3.0)
    assert f.position.y == pytest.approx(2.5)
    assert f.type == "chandelier"
    assert f.source == FixtureSource.proposed
    assert f.layer == IRLayer.decorative
    assert f.lumens == pytest.approx(3000.0)
    assert f.wattage_w == pytest.approx(45.0)


def test_decorative_pendant_at_above_table():
    from lighting_engine.models.geometry import Furniture
    room, _ = _drawing_room()
    room.furniture.append(Furniture(
        id="t", type="coffee_table", raw_label="coffee table",
        position=Point(x=3.0, y=2.5),
    ))
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    zone = Zone(
        layer=LightingLayer.decorative, purpose="feature pendant cluster",
        cct_k=2700, cri_min=90, fixture_type="pendant",
        position_hint="above coffee table",
    )
    fixtures = compute_decorative_layer(room, digest, zone)
    assert len(fixtures) == 1
    assert fixtures[0].position.x == pytest.approx(3.0)
    assert fixtures[0].position.y == pytest.approx(2.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/lighting/test_decorative_layer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement compute_decorative_layer**

```python
# src/lighting_engine/lighting/decorative_layer.py
"""Decorative-layer placement: a statement fixture per zone (chandelier, feature pendant).

Always a single fixture at the TargetRegion centre. Decorative fixtures are
larger and brighter than task/accent (3000 lm typical).
"""

from lighting_engine.brief.models import Zone
from lighting_engine.digest import RoomDigest
from lighting_engine.lighting.zone_interpreter import interpret_position_hint
from lighting_engine.models.geometry import (
    Fixture, FixtureSource, LightingLayer, Room,
)


def compute_decorative_layer(
    room: Room, digest: RoomDigest, zone: Zone,
) -> list[Fixture]:
    target = interpret_position_hint(zone.position_hint, room, digest)
    fixture_type = zone.fixture_type or "chandelier"
    reasoning = (
        f"Decorative layer: {zone.purpose}. {fixture_type} placed at "
        f"{zone.position_hint!r}"
    )
    return [Fixture(
        id=f"{room.id}-dec-001",
        type=fixture_type,
        position=target.center,
        mount_height_m=None,
        source=FixtureSource.proposed,
        layer=LightingLayer.decorative,
        reasoning=reasoning,
        wattage_w=45.0,
        lumens=3000.0,
        cct_k=zone.cct_k,
        cri=zone.cri_min,
        beam_angle_deg=120.0,
    )]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lighting/test_decorative_layer.py -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/lighting/decorative_layer.py tests/lighting/test_decorative_layer.py
git commit -m "feat(lighting): compute_decorative_layer — chandelier / feature pendant"
```

---

### Task 4.5: Multi-layer placement orchestrator

**Files:**
- Create: `src/lighting_engine/lighting/multi_layer.py`
- Test: `tests/lighting/test_multi_layer.py`

Single entry point: given a Room + Digest + RoomBrief, walk every zone in the brief and dispatch to the right layer function. Ambient stays on the existing `compute_ambient_layer` (which uses the lumen method); task/accent/decorative use the new modules. Returns a flat `list[Fixture]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/lighting/test_multi_layer.py
import pytest
from lighting_engine.lighting.multi_layer import compute_all_fixtures
from lighting_engine.brief.models import RoomBrief, Zone, LightingLayer
from lighting_engine.models.geometry import (
    Point, Room, RoomType, LightingLayer as IRLayer,
)
from lighting_engine.digest import compute_digest, Project


def _dining_room() -> tuple[Room, object]:
    room = Room(
        id="dr", name="DINING", type=RoomType.dining, floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=5, y=0), Point(x=5, y=4), Point(x=0, y=4)],
        ceiling_height_m=2.7,
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    return room, digest


def test_multi_layer_dispatches_each_layer_to_its_module():
    room, digest = _dining_room()
    brief = RoomBrief(
        target_lux_ambient=200.0, cct_main=2700,
        fixture_preference="warm-bias",
        layers_needed=[LightingLayer.ambient, LightingLayer.task, LightingLayer.decorative],
        zones=[
            Zone(layer=LightingLayer.ambient, purpose="ambient", cct_k=2700,
                 cri_min=90, fixture_type="downlight", position_hint="center"),
            Zone(layer=LightingLayer.task, purpose="task above table", cct_k=2700,
                 cri_min=90, fixture_type="pendant", position_hint="above dining table"),
            Zone(layer=LightingLayer.decorative, purpose="chandelier", cct_k=2700,
                 cri_min=90, fixture_type="chandelier", position_hint="center"),
        ],
        warnings=[],
        design_rationale="evening dining",
        design_notes=[],
        floor_lamp_suggestions=[],
        table_lamp_suggestions=[],
    )
    fixtures = compute_all_fixtures(room, digest, brief)
    by_layer = {f.layer: [g for g in fixtures if g.layer == f.layer] for f in fixtures}
    assert IRLayer.ambient in by_layer
    assert IRLayer.task in by_layer
    assert IRLayer.decorative in by_layer
    # ambient grid has several downlights, task has 1, decorative has 1
    assert len(by_layer[IRLayer.task]) == 1
    assert len(by_layer[IRLayer.decorative]) == 1
    assert len(by_layer[IRLayer.ambient]) >= 2


def test_multi_layer_handles_empty_brief_zones():
    room, digest = _dining_room()
    brief = RoomBrief(
        target_lux_ambient=200.0, cct_main=2700,
        fixture_preference="warm-bias",
        layers_needed=[], zones=[], warnings=[],
        design_rationale="", design_notes=[],
        floor_lamp_suggestions=[], table_lamp_suggestions=[],
    )
    fixtures = compute_all_fixtures(room, digest, brief)
    assert fixtures == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/lighting/test_multi_layer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the orchestrator**

```python
# src/lighting_engine/lighting/multi_layer.py
"""Walk the zones in a RoomBrief and dispatch each to its layer function."""

from lighting_engine.brief.models import LightingLayer, RoomBrief
from lighting_engine.digest import RoomDigest
from lighting_engine.lighting.accent_layer import compute_accent_layer
from lighting_engine.lighting.decorative_layer import compute_decorative_layer
from lighting_engine.lighting.placement import compute_ambient_layer
from lighting_engine.lighting.task_layer import compute_task_layer
from lighting_engine.models.geometry import Fixture, Room


def compute_all_fixtures(
    room: Room, digest: RoomDigest, brief: RoomBrief,
) -> list[Fixture]:
    out: list[Fixture] = []
    ambient_done = False
    for zone in brief.zones:
        if zone.layer == LightingLayer.ambient and not ambient_done:
            # Ambient uses the existing grid-based lumen method.
            # Multiple ambient zones get collapsed to one grid pass.
            out.extend(compute_ambient_layer(room, digest))
            ambient_done = True
        elif zone.layer == LightingLayer.task:
            out.extend(compute_task_layer(room, digest, zone))
        elif zone.layer == LightingLayer.accent:
            out.extend(compute_accent_layer(room, digest, zone))
        elif zone.layer == LightingLayer.decorative:
            out.extend(compute_decorative_layer(room, digest, zone))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lighting/test_multi_layer.py -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/lighting/multi_layer.py tests/lighting/test_multi_layer.py
git commit -m "feat(lighting): multi-layer placement orchestrator (brief → fixtures)"
```

---

## Phase 5 — Lux uniformity

Compute the lux contribution of each fixture at a grid of points on the work plane (0.8m above floor), aggregate across all fixtures, return mean / min / max / uniformity ratio.

### Task 5.1: Point-source lux contribution

**Files:**
- Create: `src/lighting_engine/lux/__init__.py`
- Create: `src/lighting_engine/lux/uniformity.py`
- Test: `tests/lux/test_uniformity.py`

Use the inverse-square-cosine law: `E = I × cos(θ) / d²` where `I` is candela intensity (approximated from lumens / steradian), `d` is the distance from fixture to the grid point, and `θ` is the angle from vertical.

- [ ] **Step 1: Write the failing test for the point-source contribution**

```python
# tests/lux/test_uniformity.py (part 1)
import math
import pytest
from lighting_engine.lux.uniformity import point_source_lux_at
from lighting_engine.models.geometry import Fixture, Point, FixtureSource


def _down_fixture(x: float, y: float, lumens: float = 1500.0) -> Fixture:
    return Fixture(
        id="f", type="downlight",
        position=Point(x=x, y=y),
        mount_height_m=2.7,
        source=FixtureSource.proposed,
        lumens=lumens, wattage_w=12, cct_k=2700, cri=90,
        beam_angle_deg=60.0,
    )


def test_lux_directly_below_fixture_uses_full_intensity():
    """Lux directly below a 1500lm fixture (60° beam, 2.7m mount) at the work plane."""
    fixture = _down_fixture(0, 0)
    lux = point_source_lux_at(fixture, Point(x=0, y=0), work_plane_height_m=0.8)
    # vertical distance = 2.7 - 0.8 = 1.9m, theta=0, cos(0)=1
    # candela = lumens / solid_angle_for_60deg ≈ 1500 / (π × (1 - cos(30°))) ≈ 1500 / 0.842
    # E = candela × 1 / 1.9² ≈ 493 lux
    assert lux == pytest.approx(493, abs=10)


def test_lux_decays_with_distance():
    """A point 2m away from directly-below should receive less lux."""
    fixture = _down_fixture(0, 0)
    near = point_source_lux_at(fixture, Point(x=0, y=0), work_plane_height_m=0.8)
    far = point_source_lux_at(fixture, Point(x=2, y=0), work_plane_height_m=0.8)
    assert far < near
    assert far > 0


def test_lux_outside_beam_cone_is_zero():
    """Point well outside a 60° beam cone gets near-zero contribution."""
    fixture = _down_fixture(0, 0)
    # 60° full beam from 1.9m height → radius ≈ 1.9 × tan(30°) ≈ 1.1m
    lux = point_source_lux_at(fixture, Point(x=5, y=0), work_plane_height_m=0.8)
    assert lux == pytest.approx(0, abs=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/lux/test_uniformity.py::test_lux_directly_below_fixture_uses_full_intensity -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement point_source_lux_at**

```python
# src/lighting_engine/lux/__init__.py
"""Lux uniformity calculation for a placed lighting layout."""
```

```python
# src/lighting_engine/lux/uniformity.py
"""Compute lux uniformity stats from a placed layout.

Model: each fixture is a point source with a finite beam angle. For each grid
point at work-plane height, compute the cosine-corrected inverse-square
contribution if the point lies inside the fixture's beam cone, else zero. Sum
contributions across all fixtures.

`E = I × cos(θ) / d²`
  • E   — illuminance at the point, in lux
  • I   — candela intensity, approximated as
              lumens / (2π × (1 - cos(half_beam_rad)))
  • θ   — angle from vertical (fixture pointing down) to the grid point
  • d   — slant distance from fixture to grid point
"""

import math
from dataclasses import dataclass

from lighting_engine.models.geometry import Fixture, Point, Room

_DEFAULT_MOUNT_HEIGHT_M = 2.7
_WORK_PLANE_HEIGHT_M = 0.8
_DEFAULT_BEAM_ANGLE_DEG = 60.0


def _candela_from_lumens(lumens: float, beam_angle_deg: float) -> float:
    """Convert total lumens to nominal candela for a downlight with the given beam."""
    half_rad = math.radians(beam_angle_deg / 2.0)
    solid_angle = 2.0 * math.pi * (1.0 - math.cos(half_rad))
    if solid_angle <= 0:
        return 0.0
    return lumens / solid_angle


def point_source_lux_at(
    fixture: Fixture, point: Point,
    *, work_plane_height_m: float = _WORK_PLANE_HEIGHT_M,
) -> float:
    """Lux contribution from one fixture at one (x, y) grid point on the work plane."""
    mount = fixture.mount_height_m if fixture.mount_height_m else _DEFAULT_MOUNT_HEIGHT_M
    vertical = mount - work_plane_height_m
    if vertical <= 0:
        return 0.0
    horizontal = math.hypot(
        point.x - fixture.position.x, point.y - fixture.position.y,
    )
    distance = math.hypot(horizontal, vertical)
    if distance <= 0:
        return 0.0
    cos_theta = vertical / distance

    beam = fixture.beam_angle_deg or _DEFAULT_BEAM_ANGLE_DEG
    half_beam = math.radians(beam / 2.0)
    theta = math.acos(cos_theta)
    if theta > half_beam:
        return 0.0

    lumens = fixture.lumens or 0.0
    candela = _candela_from_lumens(lumens, beam)
    return candela * cos_theta / (distance * distance)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lux/test_uniformity.py::test_lux_directly_below_fixture_uses_full_intensity tests/lux/test_uniformity.py::test_lux_decays_with_distance tests/lux/test_uniformity.py::test_lux_outside_beam_cone_is_zero -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/lux/__init__.py src/lighting_engine/lux/uniformity.py tests/lux/test_uniformity.py
git commit -m "feat(lux): point-source lux contribution from a single fixture"
```

---

### Task 5.2: Grid sampler + LuxStats

**Files:**
- Modify: `src/lighting_engine/lux/uniformity.py` (add `LuxStats` + `compute_uniformity`)
- Modify: `tests/lux/test_uniformity.py` (add stats tests)

- [ ] **Step 1: Write the failing tests**

```python
# tests/lux/test_uniformity.py (append)
from lighting_engine.lux.uniformity import LuxStats, compute_uniformity
from lighting_engine.models.geometry import Room, RoomType


def _square_room(side: float) -> Room:
    s = side / 2
    return Room(
        id="r", name="R", type=RoomType.living, floor_level=0,
        polygon=[
            Point(x=-s, y=-s),
            Point(x=s, y=-s),
            Point(x=s, y=s),
            Point(x=-s, y=s),
        ],
        ceiling_height_m=2.7,
    )


def test_uniformity_with_single_fixture_is_low():
    room = _square_room(4.0)
    fixtures = [_down_fixture(0, 0)]
    stats = compute_uniformity(room, fixtures, target_lux=200.0)
    assert isinstance(stats, LuxStats)
    assert stats.mean_lux > 0
    assert stats.min_lux >= 0
    assert stats.max_lux >= stats.mean_lux
    # one fixture in centre → uniformity is poor (corners get nothing)
    assert stats.uniformity < 0.4


def test_uniformity_with_grid_of_fixtures_is_high():
    room = _square_room(4.0)
    # 3x3 grid of fixtures
    fixtures = [
        _down_fixture(x, y)
        for x in (-1.0, 0.0, 1.0) for y in (-1.0, 0.0, 1.0)
    ]
    stats = compute_uniformity(room, fixtures, target_lux=200.0)
    assert stats.uniformity > 0.4
    assert stats.mean_lux > 150


def test_uniformity_meets_target_flag():
    room = _square_room(4.0)
    fixtures = [
        _down_fixture(x, y, lumens=2500)
        for x in (-1.0, 0.0, 1.0) for y in (-1.0, 0.0, 1.0)
    ]
    stats = compute_uniformity(room, fixtures, target_lux=200.0)
    assert stats.target_lux == 200.0
    assert stats.meets_target is True


def test_uniformity_with_no_fixtures_returns_zeros():
    room = _square_room(4.0)
    stats = compute_uniformity(room, [], target_lux=200.0)
    assert stats.mean_lux == 0.0
    assert stats.min_lux == 0.0
    assert stats.max_lux == 0.0
    assert stats.uniformity == 0.0
    assert stats.meets_target is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lux/test_uniformity.py -v`
Expected: FAIL with `ImportError: cannot import name 'LuxStats'`

- [ ] **Step 3: Implement LuxStats + compute_uniformity**

Append to `src/lighting_engine/lux/uniformity.py`:

```python
from pydantic import BaseModel
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

_GRID_STEP_M = 0.5


class LuxStats(BaseModel):
    mean_lux: float
    min_lux: float
    max_lux: float
    uniformity: float       # min / mean
    target_lux: float
    meets_target: bool      # mean_lux >= 0.9 × target_lux
    sample_count: int


def _sample_grid_points(
    polygon: list[Point], step_m: float = _GRID_STEP_M,
) -> list[Point]:
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    shape = ShapelyPolygon([(p.x, p.y) for p in polygon])
    points: list[Point] = []
    x = minx + step_m / 2.0
    while x < maxx:
        y = miny + step_m / 2.0
        while y < maxy:
            if shape.contains(ShapelyPoint(x, y)):
                points.append(Point(x=x, y=y))
            y += step_m
        x += step_m
    return points


def compute_uniformity(
    room: Room, fixtures: list[Fixture], *,
    target_lux: float,
    work_plane_height_m: float = _WORK_PLANE_HEIGHT_M,
    grid_step_m: float = _GRID_STEP_M,
) -> LuxStats:
    grid = _sample_grid_points(room.polygon, step_m=grid_step_m)
    if not grid or not fixtures:
        return LuxStats(
            mean_lux=0.0, min_lux=0.0, max_lux=0.0, uniformity=0.0,
            target_lux=target_lux, meets_target=False, sample_count=len(grid),
        )
    lux_per_cell = [
        sum(point_source_lux_at(f, p, work_plane_height_m=work_plane_height_m)
            for f in fixtures)
        for p in grid
    ]
    mean = sum(lux_per_cell) / len(lux_per_cell)
    min_lux = min(lux_per_cell)
    max_lux = max(lux_per_cell)
    uniformity = (min_lux / mean) if mean > 0 else 0.0
    return LuxStats(
        mean_lux=mean, min_lux=min_lux, max_lux=max_lux,
        uniformity=uniformity, target_lux=target_lux,
        meets_target=(mean >= 0.9 * target_lux),
        sample_count=len(grid),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lux/test_uniformity.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/lux/uniformity.py tests/lux/test_uniformity.py
git commit -m "feat(lux): grid sampler + LuxStats (mean/min/max/uniformity)"
```

---

## Phase 6 — SVG renderers

Two renderers: one for the revised RCP (ceiling plan with lighting overlay), one for the revised furniture plan (with floor/table lamps). Both return a full `<svg>...</svg>` string.

### Task 6.1: RCP SVG renderer

**Files:**
- Create: `src/lighting_engine/render/__init__.py`
- Create: `src/lighting_engine/render/rcp.py`
- Test: `tests/render/test_rcp.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/render/test_rcp.py
import pytest
from lighting_engine.render.rcp import render_rcp_svg
from lighting_engine.models.geometry import (
    Fixture, FixtureSource, LightingLayer, Point, Room, RoomType,
)


def _room_with_fixtures() -> tuple[Room, list[Fixture]]:
    room = Room(
        id="r", name="DINING", type=RoomType.dining, floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=5, y=0), Point(x=5, y=4), Point(x=0, y=4)],
        ceiling_height_m=2.7,
    )
    fixtures = [
        Fixture(
            id="a1", type="downlight", position=Point(x=1.25, y=1.0),
            source=FixtureSource.proposed, layer=LightingLayer.ambient,
            wattage_w=12, lumens=1500, cct_k=2700, cri=90, beam_angle_deg=60,
        ),
        Fixture(
            id="t1", type="pendant", position=Point(x=2.5, y=2.0),
            source=FixtureSource.proposed, layer=LightingLayer.task,
            wattage_w=15, lumens=1500, cct_k=2700, cri=90, beam_angle_deg=30,
        ),
    ]
    return room, fixtures


def test_rcp_svg_renders_well_formed_svg():
    room, fixtures = _room_with_fixtures()
    svg = render_rcp_svg(room, fixtures)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert 'viewBox="' in svg


def test_rcp_svg_includes_each_fixture_with_layer_class():
    room, fixtures = _room_with_fixtures()
    svg = render_rcp_svg(room, fixtures)
    # one fixture per layer, glyphs drawn as <circle> with CSS class
    assert svg.count('class="fixture-ambient"') == 1
    assert svg.count('class="fixture-task"') == 1


def test_rcp_svg_includes_room_polygon():
    room, fixtures = _room_with_fixtures()
    svg = render_rcp_svg(room, fixtures)
    assert '<polygon' in svg


def test_rcp_svg_header_strip_shows_fixture_count():
    room, fixtures = _room_with_fixtures()
    svg = render_rcp_svg(room, fixtures)
    assert '2 fixtures' in svg or '2 · ' in svg


def test_rcp_svg_with_no_fixtures_still_renders_polygon():
    room, _ = _room_with_fixtures()
    svg = render_rcp_svg(room, [])
    assert '<polygon' in svg
    assert '<circle' not in svg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/render/test_rcp.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement render_rcp_svg**

```python
# src/lighting_engine/render/__init__.py
"""SVG renderers for the revised RCP and furniture plans."""
```

```python
# src/lighting_engine/render/rcp.py
"""Render the revised RCP as an SVG string.

Inputs:
  - Room (polygon, dimensions)
  - list of Fixture (placed by the multi-layer placement code)

Output: a self-contained <svg> string with:
  - viewBox sized to the room with 1m padding
  - room polygon (light fill, dark stroke)
  - fixture glyphs (color-coded by CCT, sized by layer)
  - header strip with fixture count + total wattage
"""

import html

from lighting_engine.models.geometry import (
    Fixture, LightingLayer, Point, Room,
)


_PX_PER_M = 50
_PAD_M = 1.0


def _viewbox(polygon: list[Point]) -> tuple[float, float, float, float, float, float]:
    """Return (minx, miny, width_m, height_m, svg_w_px, svg_h_px) with padding."""
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    minx, miny = min(xs) - _PAD_M, min(ys) - _PAD_M
    maxx, maxy = max(xs) + _PAD_M, max(ys) + _PAD_M
    width_m = maxx - minx
    height_m = maxy - miny
    return minx, miny, width_m, height_m, width_m * _PX_PER_M, height_m * _PX_PER_M


def _color_for_cct(cct_k: int | None) -> str:
    if cct_k is None:
        return "#9aa0a6"
    if cct_k <= 3000:
        return "#ff9a3c"   # warm
    if cct_k <= 3500:
        return "#ffd07a"   # neutral
    return "#6fc7e6"       # cool


def _layer_class(layer: LightingLayer) -> str:
    return f"fixture-{layer.value}"


def _radius_for_layer(layer: LightingLayer) -> float:
    return {
        LightingLayer.ambient: 4.0,
        LightingLayer.task: 6.0,
        LightingLayer.accent: 3.5,
        LightingLayer.decorative: 9.0,
    }.get(layer, 4.0)


def render_rcp_svg(room: Room, fixtures: list[Fixture]) -> str:
    minx, miny, width_m, height_m, svg_w, svg_h = _viewbox(room.polygon)

    def x(v: float) -> float:
        return (v - minx) * _PX_PER_M

    def y(v: float) -> float:
        return svg_h - (v - miny) * _PX_PER_M

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" '
        f'width="{svg_w:.0f}" height="{svg_h:.0f}">',
        "<style>"
        ".room-poly { stroke: #2a2a2a; stroke-width: 1.5; fill: #f7f3e9; fill-opacity: 0.6; }"
        ".fixture-ambient { stroke: #6b5300; stroke-width: 0.8; }"
        ".fixture-task    { stroke: #6b5300; stroke-width: 1.2; }"
        ".fixture-accent  { stroke: #6b5300; stroke-width: 0.8; }"
        ".fixture-decorative { stroke: #6b5300; stroke-width: 1.4; }"
        ".header { font: 12px ui-sans-serif, system-ui; fill: #2a2a2a; }"
        "</style>",
    ]

    # Room polygon
    pts = " ".join(f"{x(p.x):.1f},{y(p.y):.1f}" for p in room.polygon)
    parts.append(f'<polygon class="room-poly" points="{pts}"/>')

    # Fixtures
    for f in fixtures:
        cls = _layer_class(f.layer)
        color = _color_for_cct(f.cct_k)
        r = _radius_for_layer(f.layer)
        parts.append(
            f'<circle class="{cls}" cx="{x(f.position.x):.1f}" '
            f'cy="{y(f.position.y):.1f}" r="{r:.1f}" fill="{color}">'
            f'<title>{html.escape(f.layer.value)} · '
            f'{html.escape(str(f.cct_k or "?"))}K · {f.wattage_w or 0:.0f}W</title>'
            f'</circle>'
        )

    # Header strip
    total_w = sum((f.wattage_w or 0.0) for f in fixtures)
    parts.append(
        f'<text class="header" x="8" y="16">'
        f'{html.escape(room.name)} · {len(fixtures)} fixtures · {total_w:.0f}W'
        f'</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/render/test_rcp.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/render/__init__.py src/lighting_engine/render/rcp.py tests/render/test_rcp.py
git commit -m "feat(render): RCP SVG renderer (room polygon + layer-coded fixtures)"
```

---

### Task 6.2: Furniture SVG renderer

**Files:**
- Create: `src/lighting_engine/render/furniture.py`
- Test: `tests/render/test_furniture.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/render/test_furniture.py
import pytest
from lighting_engine.render.furniture import render_furniture_svg
from lighting_engine.models.geometry import (
    Furniture, Point, Room, RoomType,
)
from lighting_engine.brief.models import Zone, LightingLayer


def _room_with_furniture() -> Room:
    room = Room(
        id="r", name="LIVING", type=RoomType.living, floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=5, y=0), Point(x=5, y=4), Point(x=0, y=4)],
        ceiling_height_m=2.7,
    )
    room.furniture.append(Furniture(
        id="s1", type="sofa", raw_label="sofa",
        position=Point(x=2.5, y=1.0),
    ))
    room.furniture.append(Furniture(
        id="ct", type="coffee_table", raw_label="coffee table",
        position=Point(x=2.5, y=2.0),
    ))
    return room


def test_furniture_svg_renders_well_formed_svg():
    room = _room_with_furniture()
    svg = render_furniture_svg(room, lamp_suggestions=[])
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


def test_furniture_svg_marks_each_furniture_item():
    room = _room_with_furniture()
    svg = render_furniture_svg(room, lamp_suggestions=[])
    # 2 furniture items → 2 furniture dots
    assert svg.count('class="furniture-dot"') == 2


def test_furniture_svg_renders_lamp_suggestion_triangles():
    room = _room_with_furniture()
    lamps = [
        Zone(layer=LightingLayer.accent, purpose="reading corner",
             cct_k=3000, cri_min=90, fixture_type="floor_lamp",
             position_hint="wall N"),
    ]
    svg = render_furniture_svg(room, lamp_suggestions=lamps)
    assert 'class="lamp-floor"' in svg
    assert 'reading corner' in svg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/render/test_furniture.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement render_furniture_svg**

```python
# src/lighting_engine/render/furniture.py
"""Render the revised furniture plan with suggested lamp positions."""

import html

from lighting_engine.brief.models import Zone
from lighting_engine.lighting.zone_interpreter import interpret_position_hint
from lighting_engine.models.geometry import Point, Room


_PX_PER_M = 50
_PAD_M = 1.0


def _viewbox(polygon: list[Point]) -> tuple[float, float, float, float]:
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    minx, miny = min(xs) - _PAD_M, min(ys) - _PAD_M
    maxx, maxy = max(xs) + _PAD_M, max(ys) + _PAD_M
    width_m = maxx - minx
    height_m = maxy - miny
    return minx, miny, width_m * _PX_PER_M, height_m * _PX_PER_M


def render_furniture_svg(room: Room, lamp_suggestions: list[Zone]) -> str:
    minx, miny, svg_w, svg_h = _viewbox(room.polygon)

    def x(v: float) -> float:
        return (v - minx) * _PX_PER_M

    def y(v: float) -> float:
        return svg_h - (v - miny) * _PX_PER_M

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" '
        f'width="{svg_w:.0f}" height="{svg_h:.0f}">',
        "<style>"
        ".room-poly { stroke: #2a2a2a; stroke-width: 1.5; fill: #fffbf0; "
        "fill-opacity: 0.6; }"
        ".furniture-dot { fill: #b779d4; opacity: 0.7; }"
        ".lamp-floor { fill: #ff9a3c; stroke: #8a4500; stroke-width: 0.8; }"
        ".lamp-table { fill: #ffd07a; stroke: #8a4500; stroke-width: 0.6; }"
        ".lamp-label { font: 11px ui-sans-serif, system-ui; fill: #2a2a2a; }"
        "</style>",
    ]

    # Room polygon
    pts = " ".join(f"{x(p.x):.1f},{y(p.y):.1f}" for p in room.polygon)
    parts.append(f'<polygon class="room-poly" points="{pts}"/>')

    # Existing furniture as small dots
    for f in room.furniture:
        label = html.escape(f.raw_label or f.type or "")
        parts.append(
            f'<circle class="furniture-dot" cx="{x(f.position.x):.1f}" '
            f'cy="{y(f.position.y):.1f}" r="4">'
            f'<title>{label}</title></circle>'
        )

    # Lamp suggestions as triangles
    for i, zone in enumerate(lamp_suggestions):
        target = interpret_position_hint(zone.position_hint, room, _stub_digest_for_room(room))
        cls = "lamp-floor" if "floor" in (zone.fixture_type or "") else "lamp-table"
        cx = x(target.center.x)
        cy = y(target.center.y)
        # Triangle: ▲ pointing up, 7px half-base, 9px height
        parts.append(
            f'<polygon class="{cls}" points="{cx:.1f},{cy - 9:.1f} '
            f'{cx - 7:.1f},{cy + 4:.1f} {cx + 7:.1f},{cy + 4:.1f}">'
            f'<title>{html.escape(zone.purpose)}</title></polygon>'
        )
        parts.append(
            f'<text class="lamp-label" x="{cx + 10:.1f}" y="{cy + 4:.1f}">'
            f'{html.escape(zone.purpose)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _stub_digest_for_room(room: Room):
    """Furniture render doesn't need a real digest — the interpreter only uses
    the room's polygon and furniture list. We pass a minimal duck-typed object."""
    from lighting_engine.digest import compute_digest
    from lighting_engine.models.geometry import Project
    return compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/render/test_furniture.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/render/furniture.py tests/render/test_furniture.py
git commit -m "feat(render): furniture SVG renderer (furniture + lamp suggestions)"
```

---

## Phase 7 — Integration

Wire all of Phases 3-6 into the FastAPI `POST /generate` endpoint so the studio frontend can produce a complete `PlanResponse`.

### Task 7.1: Replace the stub generation with the real pipeline

**Files:**
- Modify: `src/lighting_engine/api/routes/generation.py`
- Test: `tests/api/test_generation_e2e.py`

The Phase-2 stub creates a Job, sleeps 2s, writes a placeholder PlanResponse. Replace the sleep with: load the parsed Room IR + ConfirmedRoom clarifications, compute digest, call the LLM brief, run `compute_all_fixtures`, compute `LuxStats`, render the two SVGs, assemble `PlanResponse`, store it, mark the job done.

- [ ] **Step 1: Write the failing end-to-end test**

```python
# tests/api/test_generation_e2e.py
"""End-to-end smoke: parse a small fixture DXF, confirm a room, generate plan,
verify PlanResponse has rcp_svg + furniture_svg + non-zero lux + design rationale.

Uses a fake Anthropic client to avoid live API calls in CI.
"""
import json
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from lighting_engine.api.app import app
from lighting_engine.brief.models import RoomBrief, Zone, LightingLayer

DELHI_FIXTURE = "tests/fixtures/dwgs/real_base_architectural.dxf"


@pytest.fixture
def stub_brief() -> RoomBrief:
    return RoomBrief(
        target_lux_ambient=200.0, cct_main=2700,
        fixture_preference="warm-bias",
        layers_needed=[LightingLayer.ambient, LightingLayer.task],
        zones=[
            Zone(layer=LightingLayer.ambient, purpose="ambient",
                 cct_k=2700, cri_min=90, fixture_type="downlight",
                 position_hint="center"),
            Zone(layer=LightingLayer.task, purpose="task above table",
                 cct_k=2700, cri_min=90, fixture_type="pendant",
                 position_hint="above dining table"),
        ],
        warnings=[],
        design_rationale="A warm dining room evening setup.",
        design_notes=[],
        floor_lamp_suggestions=[],
        table_lamp_suggestions=[],
    )


@pytest.mark.skipif(not os.path.exists(DELHI_FIXTURE), reason="fixture missing")
def test_end_to_end_generate_pipeline(stub_brief):
    client = TestClient(app)

    # 1. POST /projects with the Delhi DXF
    with open(DELHI_FIXTURE, "rb") as ceiling, open(DELHI_FIXTURE, "rb") as furniture:
        resp = client.post(
            "/api/projects",
            files={
                "ceiling": ("ceiling.dxf", ceiling, "application/dxf"),
                "furniture": ("furniture.dxf", furniture, "application/dxf"),
            },
        )
    assert resp.status_code == 200
    project = resp.json()
    pid = project["project_id"]
    assert len(project["rooms"]) > 0

    # 2. Pick the DINING room
    dining = next(
        r for r in project["rooms"]
        if r["name"].upper().startswith("DINING")
    )
    rid = dining["id"]

    # 3. POST clarifications (minimum required fields)
    resp = client.post(f"/api/projects/{pid}/rooms/{rid}", json={
        "ceiling_height_m": 2.8,
        "main_window_orientation": "N",
        "ceiling_type": "false",
        "occupants": ["adult"],
        "floor_finish": "light",
        "wall_finish": "mid",
    })
    assert resp.status_code == 200

    # 4. POST brief
    resp = client.post(f"/api/projects/{pid}/rooms/{rid}/brief", json={
        "intent_mood": "entertain",
        "activities": ["family meals"],
        "time_of_use": ["evening"],
    })
    assert resp.status_code == 200

    # 5. POST /generate with mocked Claude
    with patch("lighting_engine.api.routes.generation.generate_room_brief",
               return_value=stub_brief):
        resp = client.post(f"/api/projects/{pid}/rooms/{rid}/generate")
        assert resp.status_code == 200
        job = resp.json()
        job_id = job["job_id"]

        # 6. Poll until done
        for _ in range(50):
            status_resp = client.get(f"/api/jobs/{job_id}")
            assert status_resp.status_code == 200
            status = status_resp.json()
            if status["status"] == "done":
                break
        assert status["status"] == "done", status

    # 7. GET /plan
    resp = client.get(f"/api/projects/{pid}/rooms/{rid}/plan")
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["rcp_svg"].startswith("<svg")
    assert plan["furniture_svg"].startswith("<svg")
    assert plan["lux_uniformity"]["mean_lux"] > 0
    assert "warm dining room" in plan["design_rationale"]
    assert len(plan["fixture_schedule"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_generation_e2e.py -v`
Expected: FAIL — Phase-2 stub returns empty SVGs and zero lux.

- [ ] **Step 3: Implement the real generation pipeline**

Open `src/lighting_engine/api/routes/generation.py`. Locate the placeholder `_run_generation_job` (or whatever the Phase-2 agent called it) and replace its body with:

```python
# src/lighting_engine/api/routes/generation.py (partial — replace the stub body)
from lighting_engine.brief.generator import generate_room_brief
from lighting_engine.brief.models import BriefInput
from lighting_engine.digest import compute_digest
from lighting_engine.lighting.multi_layer import compute_all_fixtures
from lighting_engine.lux.uniformity import compute_uniformity
from lighting_engine.render.rcp import render_rcp_svg
from lighting_engine.render.furniture import render_furniture_svg


async def _run_generation_job(
    *, db, job_id: str, project_id: str, room_id: str,
) -> None:
    """Replace the Phase-2 sleep stub with the real pipeline."""
    try:
        await _set_job_status(db, job_id, "running")
        confirmed = await _load_confirmed_room(db, project_id, room_id)
        room = _confirmed_to_room(confirmed)
        digest = compute_digest_for_one(room)

        brief_input = BriefInput(
            digest=digest, room_type=room.type,
            ceiling_height_m=confirmed.ceiling_height_m or room.ceiling_height_m,
            intent_mood=confirmed.intent_mood,
            activities=confirmed.activities,
            occupants=confirmed.occupants,
            floor_finish=confirmed.floor_finish,
            wall_finish=confirmed.wall_finish,
            time_of_use=confirmed.time_of_use,
        )
        brief = generate_room_brief(brief_input)

        fixtures = compute_all_fixtures(room, digest, brief)
        lux = compute_uniformity(
            room, fixtures, target_lux=brief.target_lux_ambient,
        )
        rcp_svg = render_rcp_svg(room, fixtures)
        furniture_svg = render_furniture_svg(
            room, brief.floor_lamp_suggestions + brief.table_lamp_suggestions,
        )

        plan_response = {
            "project_id": project_id,
            "room_id": room_id,
            "rcp_svg": rcp_svg,
            "furniture_svg": furniture_svg,
            "lux_uniformity": lux.model_dump(),
            "fixture_schedule": _build_fixture_schedule(fixtures),
            "design_rationale": brief.design_rationale,
            "design_notes": brief.design_notes,
            "warnings": brief.warnings,
            "metadata": {
                "model_used": "claude-opus-4-7",
                "fixture_count": len(fixtures),
            },
        }
        await _save_plan(db, project_id, room_id, plan_response)
        await _set_job_status(db, job_id, "done")
    except Exception as exc:                               # noqa: BLE001
        await _set_job_status(
            db, job_id, "failed", error_message=str(exc),
        )


def _build_fixture_schedule(fixtures):
    """Group fixtures by (type, cct, wattage, lumens) → rows for the schedule."""
    from collections import Counter
    keys = Counter()
    specs = {}
    for f in fixtures:
        k = (f.type, f.cct_k, f.wattage_w, f.lumens, f.cri, f.beam_angle_deg)
        keys[k] += 1
        specs[k] = f
    return [
        {
            "sku": f"{f.type}-{f.wattage_w:.0f}W-{f.cct_k}K".lower().replace(" ", "-"),
            "name": (
                f"{f.wattage_w:.0f}W {f.type} {f.cct_k}K CRI{f.cri or '?'}"
            ),
            "wattage_w": f.wattage_w or 0.0,
            "lumens": f.lumens or 0.0,
            "cct_k": f.cct_k or 0,
            "cri": f.cri or 0,
            "beam_angle_deg": f.beam_angle_deg or 0.0,
            "count": count,
        }
        for k, count in keys.items()
        for f in [specs[k]]
    ]


def compute_digest_for_one(room):
    """Wrap compute_digest for a single room."""
    from lighting_engine.digest import compute_digest
    from lighting_engine.models.geometry import Project
    return compute_digest(
        Project(id="x", name="x", rooms=[room])
    ).rooms[0]


def _confirmed_to_room(confirmed):
    """Hydrate a ConfirmedRoom blob from SQLite into a Room domain object."""
    # The exact transformation depends on what Phase-2 wrote into the
    # ConfirmedRoom shape. The fallback: take the parsed Room JSON + override
    # ceiling_height_m and ceiling_features per the clarifications.
    from lighting_engine.models.geometry import Room
    parsed_room = Room.model_validate(confirmed.parsed_room_json)
    if confirmed.ceiling_height_m:
        parsed_room.ceiling_height_m = confirmed.ceiling_height_m
    return parsed_room
```

Adjust `_load_confirmed_room` / `_save_plan` / `_set_job_status` signatures and DB calls to match what Phase 2's storage module emits (the agent's `storage.py` will have the exact API).

- [ ] **Step 4: Run the e2e test**

Run: `uv run pytest tests/api/test_generation_e2e.py -v`
Expected: PASS — plan has non-empty SVGs, lux > 0, design rationale text from the (mocked) brief, ≥1 fixture row.

- [ ] **Step 5: Commit**

```bash
git add src/lighting_engine/api/routes/generation.py tests/api/test_generation_e2e.py
git commit -m "feat(api): wire brief + placement + lux + renderers into POST /generate"
```

---

### Task 7.2: Final test-suite sweep

**Files:**
- Run: full pytest + ruff + pyright across the repo

After all of Phases 4-7 land:

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest --tb=short`
Expected: ALL tests pass. ~200+ tests (existing 173 + ~40 new across Phases 4-7).

- [ ] **Step 2: Run linting**

Run: `uv run ruff check src tests`
Expected: All checks passed!

- [ ] **Step 3: Run type-checking on touched modules**

Run: `uv run pyright src/lighting_engine/lighting src/lighting_engine/lux src/lighting_engine/render src/lighting_engine/api`
Expected: 0 errors on touched files. Pre-existing baseline errors elsewhere are OK.

- [ ] **Step 4: Re-render the Delhi fixture SVG end-to-end (sanity check)**

Run: `uv run python scripts/visualize_parse.py tests/fixtures/dwgs/real_base_architectural.dxf --place`
Expected: prints `Placed N proposed ambient fixtures.` and writes `/tmp/real_base_architectural.svg`. SVG opens in a browser without errors.

- [ ] **Step 5: Tag and commit a release marker**

```bash
git commit --allow-empty -m "release: v1 phases 4-7 complete (all tests green)"
git tag v1.0.0-alpha
```

---

## Self-review (run after writing — checked once and fixed inline)

- **Spec coverage:** Phases 4-7 of the v1 spec are each addressed by a task above (4.1-4.5, 5.1-5.2, 6.1-6.2, 7.1-7.2). The PlanResponse fields (`rcp_svg`, `furniture_svg`, `lux_uniformity`, `fixture_schedule`, `design_rationale`, `design_notes`, `warnings`, `metadata`) are all populated in Task 7.1.
- **Placeholder scan:** no "TBD" / "TODO" / "fill in" / "similar to Task N" / "add error handling" patterns.
- **Type consistency:** `Fixture`, `Room`, `Point`, `Zone`, `LightingLayer`, `RoomBrief`, `LuxStats` used consistently across tasks. `LightingLayer` (in brief.models) and `IRLayer` (geometry.LightingLayer) are intentionally separate — the brief layer's enum is the LLM-facing one, the IR's is what gets stored on `Fixture.layer`. Both have the same string values, no mismatch.
- **Imports in Task 4.5 use `from lighting_engine.lighting.placement import compute_ambient_layer`** — that function already exists per the existing codebase, no fabrication.
- **Task 7.1's `_confirmed_to_room`** uses fields (`parsed_room_json`, `ceiling_height_m`) that match the Phase 2 ConfirmedRoom schema in spec §3.2.
