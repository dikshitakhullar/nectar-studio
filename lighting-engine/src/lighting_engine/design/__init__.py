"""Design-layer IR for the v1 lighting agent.

Houses the two LLM-output schemas that drive the new design flow:

* `scene` — `RoomScene`, the LLM-1 scene-understanding output describing
  WHAT'S IN this specific room (wall purposes, ceiling zones, focal points).
* `intent` — `RoomDesign`, the LLM-2 design output: a flat list of
  `LightingZone` entries, each tying an intent to an anchored feature
  (wall index / focal-point index / ceiling-zone type) plus the photometric
  knobs the placement rule library needs.

This package sits alongside `lighting/`, `brief/`, `render/` and will later
host the deterministic placement rule library that consumes a
`(RoomScene, RoomDesign)` pair and emits fixture coordinates.
"""
