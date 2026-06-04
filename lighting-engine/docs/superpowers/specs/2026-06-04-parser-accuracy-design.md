# Parser accuracy + uncertainty overhaul — Design

**Date:** 2026-06-04
**Author:** Dikshita (founder) + Claude (drafting)
**Status:** Draft pending review

## 1. Problem & goal

The current deterministic parser produces visibly incorrect output on real residential DWGs:

- **Polygon ↔ label assignment is wrong** for some rooms (the foundational error; cascades into every downstream layer).
- **Door/window attribution is mis-distributed** — Drawing Room shows 0 doors while Puja Room shows 3.
- **Furniture parsing misses ~70% of items** — beds, sofas, dining tables exist as block references + polylines without text labels and the current code only walks TEXT entities. AutoCAD block-IDs like `A$C40b9ed5b` are counted as furniture, inflating the noise.
- **No uncertainty surfacing** — every parsed item is presented to the designer with equal weight; there's no "we're not sure about this — confirm?" moment. The "no part inside a house can be unlabeled" architectural invariant is not enforced.

**Goal:** rebuild the parse pipeline as three layers — fast deterministic Layer 1, async Claude-vision Layer 2 (verifies, disambiguates, augments), and designer-in-the-loop Layer 3 (only when both prior layers are unsure). Every parsed entity carries `confidence` + `provenance` so the studio can audit and the designer can intervene precisely where it matters.

## 2. Architecture

Three layers, one shared IR. Each entity (Room, Door, Window, Furniture) flows through all three; each layer can update it and stamps its provenance.

```
DXF upload
   │
   ▼
┌─ Layer 1: Deterministic parser ─────────────────────────┐
│  walls → wall-graph → cells → polygon-label matching    │
│  + INSERT block extraction (furniture footprints)       │
│  + door symbol detection + window glazing detection     │
│  Emits: IR with confidence + uncertainty flags          │
│  Upload returns NOW (~5s); status=verifying per room    │
└──────────────┬──────────────────────────────────────────┘
               ▼
┌─ Layer 2: Claude vision pass (async background) ────────┐
│  For each room with any uncertainty (parallel up to N): │
│    render PNG crop (room + neighbors, ~15m radius)      │
│    call Claude with: crop, label, candidates, batched   │
│       Qs (polygon? doors? furniture? add missing?)      │
│  Plus: one whole-plan call for LOBBY arm recovery       │
│  Rooms transition: verifying → ready / needs_attention  │
└──────────────┬──────────────────────────────────────────┘
               ▼
┌─ Layer 3: Designer-in-the-loop ─────────────────────────┐
│  Studio shows "X items to confirm" on needs_attention   │
│   rooms. Designer confirms / picks alternative / fixes  │
│   manually. Provenance flips to "designer".             │
└─────────────────────────────────────────────────────────┘
```

## 3. Data model

### 3.1 Per-entity fields (added to `Room`, `Door`, `Window`, `Furniture`)

```python
confidence: float          # ∈ [0, 1]; 1.0 = parser certain by construction
provenance: Literal["parser", "llm", "llm_uncontested", "designer"]
llm_status: Literal["unchecked", "verified", "flagged_as_noise"]
alternatives: list[Alternative] | None  # set by LLM when alternatives existed

class Alternative(BaseModel):
    value: str | dict[str, Any]   # type depends on the field being alternated
    confidence: float
    reason: str                    # one-sentence explanation Claude returned
```

`provenance` values:
- `parser` — deterministic Layer 1 set this
- `llm` — Layer 2 set this with high confidence (≥0.8); silent to the designer
- `llm_uncontested` — Layer 2 was uncertain AND the designer hit Continue without explicitly confirming. Captured for audit; behaviorally equivalent to `llm`.
- `designer` — Layer 3 designer explicitly confirmed, picked alternative, or fixed manually

The `Alternative.value` is typed at the schema level per entity field (a discriminated union — door-type alternatives are `str`, position alternatives are `Point`, etc.) — `str | dict` is the most permissive serialization.

`llm_status = "flagged_as_noise"` is what drops AutoCAD block-IDs from the visible furniture list — Claude says "this isn't real furniture"; the item stays in the DB for audit but the UI filters it.

### 3.2 Room-level status (per-room badge in the studio)

```python
status: Literal[
    "parsing",          # Layer 1 still running (rare; usually instant)
    "verifying",        # Layer 2 running in the background
    "ready",            # All entities confidence >= 0.8; silent for designer
    "needs_attention",  # ≥1 entity below threshold; designer confirms
    "manual",           # Layer 2 unavailable or failed; designer reviews all
]
```

### 3.3 Project-level verification flag

Separate from per-room status, the project carries a global flag:

```python
verification_mode: Literal["enabled", "disabled"]
```

- `enabled` (default): Layer 2 attempts to verify on upload
- `disabled`: Layer 2 skipped entirely; every room ships as `manual`

Set to `disabled` automatically when: feature flag is off, `ANTHROPIC_API_KEY` missing, or cost hard cap exceeded for this upload. Designers see the same UX as a per-room `manual` (review everything) — `disabled` is just the explanation in the audit log.

### 3.3 Migration

Existing DB rows backfill: `confidence = 1.0`, `provenance = "parser"`, `llm_status = "unchecked"`, `alternatives = None`, `status = "ready"`. Backwards-compatible — existing projects keep working as before.

## 4. Layer 1: Deterministic parser changes

### 4.1 New module: INSERT block extraction

**File:** `lighting-engine/src/lighting_engine/parser/furniture_geometry.py`

Walks the DXF for `INSERT` entities (block references). Resolves each block's footprint polygon from its `BLOCK` definition (bounding box of the block's graphics, transformed by position/rotation/scale). Recurses into nested INSERTs up to depth 3.

Filters at extraction:
- AutoCAD block-IDs (regex: `^A\$[A-Z]{1,2}[0-9a-fA-F]+$`) → drop the label, keep the footprint (with `raw_label = None`, `type = "unknown"`, `confidence = 0.5`)
- Heuristic classify by block name when obvious:
  - `BED-*`, `BD-*`, `*BED*` → type = "BED" (confidence 0.9)
  - `SOFA-*`, `SF-*`, `*SOFA*` → type = "SOFA" (confidence 0.9)
  - `DT-*`, `DINING-*`, `DINING TABLE` → type = "DINING_TABLE" (confidence 0.9)
  - All others → type = "unknown" (confidence 0.5)
- Emits `Furniture` with `footprint: list[Point]` set (not just position).

### 4.2 Confidence scoring on existing assignments

The parser stops treating its output as ground truth. Each entity gets a confidence at parse time; low scores ride into Layer 2 as "please verify this".

| Entity | Low-confidence triggers |
|---|---|
| Room polygon ↔ label | Label outside any cell (0.2); multiple labels in one cell (0.4); cell with no label = "orphan cell" (0.3); polygon area > 3× or < 1/3 typical for room type (0.5) |
| Door | Multiple doors mapped to the same wall edge (0.5); door symbol not near any wall midpoint (0.3); door's wall shared between 2+ rooms with no clear owner (0.4) |
| Window | Window-layer line not adjacent to any interior wall (0.2); window on a wall facing terrace/courtyard (0.4 — candidate French window) |
| Furniture | Block-ID-only labels → type=unknown (0.5); INSERT footprint partially outside its containing room (0.4) |

A reference table `TYPICAL_ROOM_AREAS_M2` codifies the "typical for room type" comparison:

```python
TYPICAL_ROOM_AREAS_M2 = {
    "bedroom": 14, "master_bedroom": 22, "guest_bedroom": 12,
    "kitchen": 12, "dining": 16, "drawing_room": 30, "family_lounge": 22,
    "study": 10, "bathroom": 5, "puja_room": 4, "store_room": 4,
    "lobby": 15, "foyer": 8, "dress": 6, "balcony": 6,
}
```

### 4.3 LOBBY L-shape support

**File:** `lighting-engine/src/lighting_engine/parser/lobby_recovery.py` (new)

The current `wall_graph.polygonize` returns minimum-area faces — a real L-shaped LOBBY gets split into 2+ cells. This module:

1. After polygon-label matching, find "orphan cells" (extracted polygons no label claims)
2. For each orphan, find candidate parents — labeled rooms that share walls AND are passage-type (LOBBY, PASSAGE, FOYER, HALLWAY, per `room_tier.is_passage_type`)
3. **Tie-breaker** when an orphan touches multiple passage candidates: parent that shares MORE wall length wins; if tied within 10%, mark uncertain (Layer 2 resolves)
4. Emit candidates with confidence ≤ 0.6 — does NOT perform the merge. Layer 2's whole-plan call confirms.

### 4.4 Cleanup of existing modules

- `parser/furniture_merge.py`: drop AutoCAD block-IDs at the *candidate seen* stage (would reduce the 31 → ~18 real candidates on Delhi)
- `parser/door_anchor.py` + `door_detection.py`: emit per-door `confidence`
- `parser/window_filter.py`: emit per-window `confidence`
- `parser/pipeline.py`: orchestrate the new flow — call `furniture_geometry.extract`, then `lobby_recovery.find_candidates`, emit IR with confidence + llm_status on every entity

## 5. Layer 2: Claude vision disambiguation

### 5.1 New package: `lighting-engine/src/lighting_engine/llm/`

| Module | Responsibility |
|---|---|
| `disambiguator.py` | Orchestrator: iterates rooms with uncertainty, fires parallel room calls, merges results back into IR |
| `room_render.py` | Pure function: `(project, room_id) -> bytes (PNG)`. Uses matplotlib (existing dep). Renders room polygon + neighbors within 15m + walls + parsed candidates as overlays. Background grayscale, candidates colored, uncertain items highlighted red. ~600×600px. |
| `prompts.py` | System + user templates. System prompt cached (Delhi vocab, response format, examples). |
| `schemas.py` | Pydantic models for Claude's structured output, one per decision type |

### 5.2 Per-room call shape

Per claude-api guidance — use `claude-opus-4-7`, `thinking: {type: "adaptive"}`, `output_config.format` for structured JSON, prompt caching on the system prefix.

**Claude sees:**
- Image: rendered PNG crop (~1500 vision tokens per call)
- Text: structured JSON listing every uncertain item in the room and a "did we miss any furniture?" question

**Claude returns** (validated structured output): one decision per question. Each decision: `{ value, confidence, reason, alternatives? }`.

**Parallelism:** disambiguator runs up to N rooms concurrently. N adjusts dynamically based on `anthropic-ratelimit-*` response headers — not a hardcoded value.

### 5.3 LOBBY arm recovery call (cross-room, one per plan)

- Render: full plan with orphan cells highlighted red, all labeled rooms shown with names
- Question: for each orphan cell, which labeled room does it extend into? Or is it truly unlabeled (designer decides)?
- Same structured-output shape

### 5.4 Where it plugs in

`api/routes/projects.py` upload handler: after Layer 1 completes, response returns immediately with rooms in `verifying` status. A background task (`fastapi.BackgroundTasks` in v1; worker queue in v1.1) calls `disambiguator.verify_project(project_id)`. Each room's DB record updates as the LLM finishes — `verifying → ready` or `needs_attention`.

### 5.5 Cost & latency budget (per Delhi-sized plan)

- ~6-8 first-class rooms with uncertainty → 6-8 parallel room calls
- ~1500 vision tokens per image + ~3000 text tokens question, ~1000 tokens response
- System prompt cached → ~90% input-cost reduction on subsequent calls
- **Cost: ~$0.10–$0.20 per plan upload** (cached prompt + minimal vision tokens)
- **Latency: 15–25s** total with parallel calls
- LOBBY call: ~$0.05 extra, runs in parallel with room calls

### 5.6 Retry & failure

- Per-room: 3 retries with exponential backoff (2s, 4s, 8s); on final fail → room status = `manual`
- Invalid structured output: treat as transient, retry once
- Anthropic rate-limit: respect headers, reduce concurrency dynamically
- All calls fail (no API key, outage): project → `verification_disabled` mode; every room `manual`
- Per-upload cost hard cap: $1.00. If projected cost exceeds, short-circuit; all uncertain rooms → `manual`. Log event.

## 6. Layer 3: Designer-in-the-loop UX

### 6.1 Upload flow

`POST /api/projects` returns as soon as Layer 1 finishes (~5s). Rooms list returns with `verification_status = "verifying"` per first-class room. Studio routes to `/studio/rooms` (picker).

The picker polls `GET /api/projects/{id}/rooms` for status updates. Backoff: 2s → 5s → 10s, capped; stop polling when all rooms reach a terminal state (`ready`, `needs_attention`, `manual`).

### 6.2 Rooms picker — per-room badge

| Status | Visual | Designer action |
|---|---|---|
| `verifying` | amber pulsing dot | View disabled; tooltip "AI is checking this room" |
| `ready` | green dot | Click → straight into the existing flow (basics → walls → furniture → brief) |
| `needs_attention` | amber border + "N to confirm" pill | Click → opens room with **confirm panel** docked at top |
| `manual` | neutral icon, "Review manually" | Click → opens room; every parsed item is designer-must-confirm |

### 6.3 Confirm panel (docked at top, only on `needs_attention` rooms)

One card per uncertain item, capped at 5 visible at a time. Priority sort: polygon assignment > LOBBY merge > door > furniture-add > furniture-classify.

Card types:

- **Polygon-uncertain** — mini-map shows the proposed polygon + alternatives outlined. Designer clicks the right one.
- **Door/window-uncertain** — door symbol in context + proposed type & destination + alternatives.
- **Furniture-classify** — footprint + Claude's typed alternatives. Designer picks type or "not real" (drops the item, `llm_status = "flagged_as_noise"`).
- **Furniture-add** — Claude proposes adding (parser missed). Designer accepts or rejects.
- **LOBBY merge** — "We think this region extends LOBBY into an L-shape. Confirm or reassign."

Each card has 3 actions: **Confirm** (Claude's pick), **Pick alternative** (dropdown), **It's wrong** (designer fixes manually).

### 6.4 Skip / continue semantics

If designer hits Continue without confirming all cards: unconfirmed items default to Claude's current value, `provenance` set to `"llm_uncontested"` (a sub-value of `"llm"` for audit purposes). Designer's silence = implicit confirm. The "Skip — confirm later" button is just a UX label for the same path.

### 6.5 New endpoints

- `GET /api/projects/{pid}/rooms/{rid}/confirmations` → returns uncertain items + Claude proposals + alternatives. Studio renders confirm panel from this.
- `POST /api/projects/{pid}/rooms/{rid}/confirmations` → submits designer answers. Each answer updates the underlying entity (Room polygon, Door, Window, Furniture). `provenance` flips to `"designer"`.

### 6.6 Position coordinate frame

When Claude returns a position for a proposed-to-add piece of furniture, the position is in **room-local meters** (same frame as `room.polygon_inferred`). Studio renders it directly on the existing mini-map.

## 7. Error handling matrix

| Failure | Behavior |
|---|---|
| Layer 1 parse fails | Existing 422 (unchanged) |
| Single room LLM call fails | 3 retries; on final fail → room `status = manual` |
| All room calls fail | Project → `verification_disabled`; all rooms `manual`; upload still works |
| Claude returns invalid structured output | One retry; second fail → room `manual` |
| Designer submits invalid confirmation | 400 with field-level errors |
| LOBBY recovery call fails | Orphan cells stay unlabeled; studio prompts "we found N unlabeled regions — assign room" |
| Per-upload cost hard cap exceeded | Short-circuit Layer 2; all uncertain rooms `manual` |

## 8. Testing strategy

| Layer | Test type | What's covered |
|---|---|---|
| Deterministic parser changes | Unit, no LLM | Block-ID regex on real samples; INSERT extraction on synthetic + Delhi fixtures; confidence trigger conditions; LOBBY orphan candidate identification + tie-breaker |
| LLM disambiguator | Integration, mocked Anthropic client | Prompt construction, image rendering, response merging, retry logic, structured-output validation, mocked failures |
| End-to-end with real Anthropic | Golden file on Delhi fixture, gated on `ANTHROPIC_API_KEY` env | Snapshot expected per-room confidence + verification_status counts. Re-snapshot when prompt changes. |
| Studio | Component tests for ConfirmCard wrapper; existing page tests for rooms picker / room flow unchanged | |
| `room_render.py` | Snapshot test | PNG hash against a fixture |

## 9. Rollout — feature flag

Env var `LIGHTING_ENGINE_LLM_VERIFY_ENABLED` (default false in v1.0.x; flip on for v1.1).

- **Off**: skip Layer 2 entirely; every first-class room ships as `ready` with confidence=1.0. Backwards-compatible — current behavior preserved.
- **On**: Layer 2 runs as designed.

Lets us ship parser changes + IR additions independently, then enable LLM verification when comfortable.

## 10. v1.1 deferred items (explicit)

- Server-sent events instead of polling
- Provenance audit sidebar in studio ("AI-resolved" subtle badge on items where `provenance = "llm"`, click to see Claude's reasoning)
- Anthropic spend tracking dashboard (admin view)
- LOBBY recovery on multi-floor plans (v1 = single-floor only)
- Disambiguator's "missing furniture" suggestion across non-furniture rooms (toilets get fixtures, kitchens get appliances)
- Replace `fastapi.BackgroundTasks` with a worker queue (Celery / arq) for the async pipeline
- Prompt-cache key versioning for safe prompt rollouts

## 11. Out of scope for this spec

- Round-trip back to DXF (output a corrected DWG) — v1.2
- Multi-floor LOBBY recovery — v1.1
- Lighting design itself — handled by separate spec `2026-06-03-v1-design.md`
- Computer-use / Claude-agentic-loop interfaces — current scope is a single vision call per room
