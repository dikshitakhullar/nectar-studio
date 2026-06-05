# v1 Lighting Agent — MVP Reframe

**Date:** 2026-06-05
**Status:** Approved — implementation starting

## 0. Problem

The current pipeline treats lighting design as: "parse → LLM picks abstract zones → naive geometric placement." On Delhi residential plans this produces designer-quality failures: 7 wall grazers on a 5.5m wall (gallery spacing), grazers behind windows, lamps stacking at the polygon centroid, generic "bedroom = 200 lux" recipes that ignore where the bed actually sits.

The founder's diagnosis (2026-06-04): *"we are just doing something very basic. we need to have a good understanding of the room layout, THEN only will we say where the lights need to be put. Not a standing — in a bedroom put x lumens."*

## 1. Goal

Replace the thin brief + naive placement with a contextual two-layer LLM design that reads the **specific** room's layout before placing fixtures. MVP must produce a lighting plan that impresses a real designer for at least one canonical room (the Delhi BEDROOM-2 reference) — not because it's perfect, but because every fixture has a *reason* tied to THIS room's actual features.

## 2. Scope

### In MVP
- New IR: `RoomScene` (wall purposes, focal points, ceiling zones) and `LightingZone` (per-intent design unit)
- LLM-1: Scene understanding — vision call producing `RoomScene` from rendered floor + furniture (+ optional RCP)
- LLM-2: Design intent — proposes `LightingZone` list from scene + designer's mood + IS 3646 standards
- Placement-rule library — one deterministic rule per intent (cove_uplight, bedside_reading, tv_backlight, accent_artwork, task_dining, perimeter_cove, ambient_downlight, etc.)
- Hard-constraint enforcement at placement time: no fixture on furniture, no grazer over door/window, residential count caps, min wall offsets
- RCP renderer + furniture-plan renderer updates so each fixture's intent + rationale is visible
- Studio: read-only output viewer (existing pack page); shows per-zone rationale

### NOT in MVP (explicit deferrals)
- **RCP PDF vision parsing** — v1.1. MVP uses the `ceiling_type` enum + a `has_cove`/`has_level_change` flag the designer toggles in room-basics.
- **Wall drawings (per-wall elevations)** — v1.1. MVP delivers RCP + furniture plan only.
- **Canvas editor** — v1.2. MVP is read-only; designer comments via free-text "what's wrong" field; we regen on feedback.
- **Multi-room scenes / circuits / control programming** — v2.
- **Parser-accuracy improvements** — separate spec (`2026-06-04-parser-accuracy-design.md`), runs in parallel.

## 3. Architecture

```
Inputs                Layer 2 (LLM)             Layer 3 (Rules)        Output
────────────────────  ──────────────────────    ─────────────────      ────────────
Architectural DWG  ┐                                                   Revised RCP
Furniture DWG      │                                                   SVG
Room basics        ├─► Scene understanding   ─► RoomScene  ─┐
(ceiling_type,     │   (vision, ~$0.05/room)                │
 has_cove,         │                                        │          Furniture+lamps
 wall texts)       │                                        │          SVG
                   │                                        ▼
                   │                                  Design intent
                   │                                  (~$0.05/room)
                   │                                  produces             ┌─ Fixture schedule
                   │                                  LightingZone[]       │
                   │                                        │              │
                   │                                        ▼              │
                   └────────────────────────► Placement rule library ──────┘
                                                  (one rule per intent;
                                                   enforces hard rules)    Design rationale
                                                                           (per zone)
```

Two LLM calls per room — each parallel-safe across rooms. Total cost target: ≤ $0.15 per room with prompt caching.

## 4. New data models

### `RoomScene` (output of LLM-1)

```python
class WallPurpose(BaseModel):
    wall_index: int                            # polygon edge index
    purpose: Literal[
        "headboard", "tv", "artwork", "blank", "fluted",
        "french_window", "balcony_door", "entry", "wardrobe",
        "feature_panel", "mirror", "bookshelf",
    ]
    features: list[str] = []                   # free-text Claude observations
    confidence: float

class CeilingZone(BaseModel):
    type: Literal["cove", "flat", "level_change", "fluted", "tray"]
    description: str                           # "perimeter cove around central LVL ±0"
    confidence: float

class FocalPoint(BaseModel):
    type: Literal["dining_table", "bed", "sofa", "desk",
                  "vanity", "kitchen_island", "puja_altar"]
    position: Point                            # room-local
    purpose_hint: str                          # "head end of bed faces north"

class RoomScene(BaseModel):
    walls: list[WallPurpose]
    ceiling: list[CeilingZone]
    focal_points: list[FocalPoint]
    notes: str                                 # Claude's overall scene narrative
    confidence: float
```

### `LightingZone` (output of LLM-2)

Replaces the current `Zone` model. Each zone is one design intent tied to a specific feature.

```python
class LightingZone(BaseModel):
    intent: Literal[
        "cove_uplight", "level_change_uplight", "fluted_grazing",
        "perimeter_ambient", "central_ambient",
        "bedside_reading", "headboard_wash", "tv_backlight",
        "accent_artwork", "accent_niche", "accent_mirror",
        "task_dining", "task_kitchen", "task_desk", "task_vanity",
        "decorative_chandelier", "decorative_pendant", "decorative_floor_lamp",
    ]
    target_feature_ref: str    # e.g. "wall_2", "focal_0", "ceiling_cove"
    fixture_archetype: str     # "strip", "downlight", "pendant", "wall_sconce", ...
    cct_k: int
    cri_min: int
    beam_deg: int | None       # None for diffuse strips
    target_lux: float | None   # None for accent layers
    rationale: str             # Claude's one-sentence reason

class RoomDesign(BaseModel):
    zones: list[LightingZone]
    overall_rationale: str     # 2-3 sentence design narrative
```

## 5. Layer 2: LLM calls

Per claude-api defaults — `claude-opus-4-7`, `thinking: {type: "adaptive"}`, structured output via `output_config.format`, prompt caching on the system prompt.

### 5.1 Scene understanding

**Input:** rendered PNG (floor plan + furniture overlay + ceiling type annotation) + structured text (room dims, ceiling height, designer's wall_text descriptions).

**System prompt:** Delhi residential vocabulary, "every wall has a purpose," "identify focal points by their typical furniture signatures," response schema explanation.

**Output:** `RoomScene` (structured).

### 5.2 Design intent

**Input:** the `RoomScene` from 5.1 + designer's mood/activities/occupants + IS 3646 standards snippet + the fixture catalog.

**System prompt:** layered lighting (ambient/task/accent/decorative), Indian residential conventions, "one intent per zone tied to a specific feature in the scene."

**Output:** `RoomDesign` (list of `LightingZone`s).

Both calls share the same `VerifyClient` wrapper (retry, prompt cache, structured output, vision).

## 6. Layer 3: Placement rule library

One module per intent, each exposes `place(zone: LightingZone, room: Room, scene: RoomScene) -> list[Fixture]`.

| Intent | Rule (one-liner) |
|---|---|
| `cove_uplight` | Strip along the cove pocket geometry; 1m segments; 3000K warm |
| `level_change_uplight` | Strip on underside of the raised LVL slab perimeter |
| `fluted_grazing` | Grazers at 30cm spacing above the fluted strip; aim 0.3m off wall |
| `perimeter_ambient` | Downlights at 1.2m from wall, 1.5m apart, on solid walls only |
| `central_ambient` | Downlights in 2x2 / 3x3 grid in the central ceiling zone |
| `bedside_reading` | 2 sconces flanking bed at 0.9m mount height; 60cm from bed edges |
| `headboard_wash` | 1-2 picture lights above headboard; 2700K warm |
| `tv_backlight` | Strip behind TV at 30cm offset; 6500K cool dim |
| `accent_artwork` | 1 spotlight at 0.9-1.5m wall offset; 30° beam; aim at art centroid |
| `accent_niche` | 1 mini-downlight inside niche; warm |
| `task_dining` | Pendant centered above dining table; 75cm above table |
| `task_kitchen` | Downlights over counter at 60cm spacing |
| `decorative_chandelier` | Single fixture at room centroid; 1.8m above floor |
| ... | ... |

**Hard rules every placement function calls:**
- `no_fixture_on_furniture(position, room)` — checks all furniture footprints
- `no_grazer_over_opening(wall_index, room)` — already implemented in accent_layer
- `respect_count_cap(intent, count)` — residential caps from constants
- `min_wall_offset(position, room)` — fixtures stay ≥ 30cm from walls

## 7. Renderers

- **RCPRenderer:** existing, extend to draw cove/level-change indicator + fixture rationale on hover
- **FurniturePlanRenderer:** existing, ensure lamp spreading is right (already patched)
- **FixtureSchedule:** existing, add `intent` column
- **DesignRationale:** new — per zone, the LLM-2's rationale; plus overall_rationale at top

## 8. Acceptance criteria

The Delhi BEDROOM-2 reference plan should produce:
- A scene with `headboard` purpose on one wall, `french_window` on the balcony-facing wall, `cove` on ceiling
- Lighting zones: `cove_uplight` + `bedside_reading` + `accent_artwork` (if any wall is artwork) + `perimeter_ambient`
- No fixture on the bed footprint
- No wall grazer behind the French window
- Designer rationale that mentions the bed position and the ceiling cove specifically

If a designer reading the output says "I would tweak X" — fine. If they say "this isn't even close" — fail.

## 9. Cost & latency budget

- Per room: ≤ $0.15 (two cached LLM calls + minimal vision tokens)
- Per generation: ≤ 30s end-to-end including both LLM calls
- Failure path: if either LLM call fails, fall back to current generation pipeline (no regression)

## 10. Migration

- `RoomBrief` (existing) is replaced by `RoomDesign`. `RoomBrief` model stays in the repo, deprecated, used by no path.
- Existing pack page reads the new `RoomDesign`; rationale section gets the per-zone explanations.
- Feature flag `LIGHTING_ENGINE_USE_V1_DESIGNER` defaults OFF for the first commits; flip ON when MVP is integration-tested.

## 11. Out of scope (firm)

- RCP PDF vision parsing (v1.1)
- Wall drawing renderer (v1.1)
- Canvas editor (v1.2)
- Multi-room / scene programming / circuits (v2)
- Photometric simulation (v2)
