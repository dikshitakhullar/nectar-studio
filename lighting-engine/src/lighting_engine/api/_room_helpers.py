"""Local helpers used by the routes.

These live in the API package (not the domain layer) so that Phase 1's
tier-classifier — when it lands — can replace ``classify_tier`` without
forcing a change to the HTTP-facing schemas.
"""

from lighting_engine.api.schemas import (
    ConfirmedRoom,
    RoomDims,
    RoomSummary,
    RoomTier,
)
from lighting_engine.models.geometry import Point, Room, RoomType


# Spec §3.1 — room tier mapping. The parser's RoomType vocabulary is narrower
# than the spec's (which lists 9 first-class + 4 generic types), so this is a
# best-effort mapping for v1; Phase 1 will deliver a proper classifier whose
# output we'll prefer over this fallback.
_HIDDEN_TYPES: frozenset[RoomType] = frozenset({
    RoomType.bathroom,
    RoomType.outdoor,
    RoomType.staircase,
})

_GENERIC_TYPES: frozenset[RoomType] = frozenset({
    RoomType.foyer,
    RoomType.hallway,
})


def classify_tier(room_type: RoomType) -> RoomTier | None:
    """Return the tier the room belongs to, or ``None`` if it should be
    hidden from the studio picker entirely."""
    if room_type in _HIDDEN_TYPES:
        return None
    if room_type in _GENERIC_TYPES:
        return RoomTier.generic
    # Unknown rooms still surface — the designer can label them.
    return RoomTier.first_class


def room_dims(polygon: list[Point]) -> RoomDims:
    """Bounding-box dims for the room polygon (meters)."""
    if not polygon:
        # Defensive — the parser shouldn't emit empty polygons, but pydantic
        # would reject zero so the route layer can replace this with a 400.
        return RoomDims(length_m=0.01, width_m=0.01)
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    width = max(xs) - min(xs)
    length = max(ys) - min(ys)
    return RoomDims(
        length_m=max(length, 0.01),
        width_m=max(width, 0.01),
    )


def confirmed_room_from_parsed(room: Room, tier: RoomTier) -> ConfirmedRoom:
    """Project a parsed ``Room`` into a fresh ``ConfirmedRoom`` blob.

    All clarification fields stay ``None`` — the studio fills them in via the
    POST endpoints. Provenance for the parser-sourced fields is recorded
    eagerly so debug logs can answer "where did this value come from?".
    """
    provenance: dict[str, str] = {
        "type_inferred": "parser",
        "polygon_inferred": "parser",
        "doors_parsed": "parser",
        "windows_parsed": "parser",
        "furniture_parsed": "parser",
        "ceiling_features_parsed": "parser",
    }
    return ConfirmedRoom(
        id=room.id,
        name=room.name,
        type_inferred=room.type,
        polygon_inferred=list(room.polygon),
        doors_parsed=list(room.doors),
        windows_parsed=list(room.windows),
        furniture_parsed=list(room.furniture),
        ceiling_features_parsed=list(room.ceiling_features),
        tier=tier,
        provenance=provenance,
    )


def room_summary_from_record(
    *,
    room_id: str,
    name: str,
    tier: RoomTier,
    status: str,
    confirmed: ConfirmedRoom,
) -> RoomSummary:
    """Build a wire-format ``RoomSummary`` from the stored ConfirmedRoom blob."""
    return RoomSummary(
        id=room_id,
        name=name,
        type=confirmed.type_confirmed or confirmed.type_inferred,
        dims=room_dims(confirmed.polygon_inferred),
        polygon=list(confirmed.polygon_inferred),
        doors=list(confirmed.doors_parsed),
        windows=list(confirmed.windows_parsed),
        confidence=1.0,
        tier=tier,
        status=status,
    )
