"""Classify each parsed room into a v1 design-flow tier.

The studio's room picker (`/studio/rooms`) only surfaces rooms whose tier is
`first_class` or `generic`. `hidden` rooms (toilets, storage, terraces, etc.)
are filtered out before they ever reach the designer — they don't pay for
lighting-design effort in Indian residential work.

This module exposes a single pure function, `classify_room_tier(room_type,
name)`, that returns a `RoomTier` from §3.1 of the v1 spec. The classifier
matches `RoomType` first (the parser's strongest signal) and then falls back
to case-insensitive name-substring matching for the cases where the parser
inferred `RoomType.unknown` but the architect wrote a clear room name like
"DRAWING ROOM" or "PUJA ROOM".

Name-substring matching uses fragments that:
  - DON'T collide between tiers (e.g. "BEDROOM" is unique to first_class —
    "MASTER BEDROOM" / "GUEST BEDROOM" all match it).
  - HANDLE Indian residential vocabulary (DRAWING, PUJA, FAMILY LOUNGE,
    BAR) that the generic RoomType enum doesn't cover.
"""

from lighting_engine.models.geometry import RoomTier, RoomType

# Name fragments per tier, matched case-insensitively as substrings. Order
# of TIER LOOKUP matters — see `classify_room_tier` for the priority rule
# ("hidden" wins ties so utility names like "MASTER DRESS" with the word
# "MASTER" don't accidentally bleed into first-class).
_FIRST_CLASS_NAME_HINTS: tuple[str, ...] = (
    "drawing",
    "living",
    "dining",
    "bedroom",
    "lounge",
    "family lounge",
    "bar",
    "kitchen",
    "study",
    "wfh",
    "puja",
)

_GENERIC_NAME_HINTS: tuple[str, ...] = (
    "foyer",
    "entrance",
    "lobby",
    "passage",
    "dress",
)

_HIDDEN_NAME_HINTS: tuple[str, ...] = (
    "toilet",
    "bath",
    "bathroom",
    "storage",
    "store",
    "utility",
    "washing",
    "courtyard",
    "terrace",
    "staircase",
    "stair",
    "balcony",
    "shaft",
    "lift",
    "pantry",
    "double height",
)

# RoomType → tier. `unknown` is intentionally absent so the name-substring
# fallback takes over for those.
_TYPE_TO_TIER: dict[RoomType, RoomTier] = {
    RoomType.living: RoomTier.first_class,
    RoomType.dining: RoomTier.first_class,
    RoomType.bedroom: RoomTier.first_class,
    RoomType.kitchen: RoomTier.first_class,
    RoomType.study: RoomTier.first_class,
    RoomType.foyer: RoomTier.generic,
    RoomType.hallway: RoomTier.generic,
    RoomType.bathroom: RoomTier.hidden,
    RoomType.staircase: RoomTier.hidden,
    RoomType.outdoor: RoomTier.hidden,
}


def classify_room_tier(room_type: RoomType, name: str) -> RoomTier:
    """Return the design-flow tier for a parsed room.

    Priority order:
      1. `RoomType` enum match (the parser already classified — trust it).
         `RoomType.unknown` falls through to name matching.
      2. Hidden-name match. A name containing "TOILET" or "STORAGE" forces
         hidden regardless of any first-class fragment that happens to also
         be in the name. This handles "STAIR LOBBY" (hidden) vs "LOBBY"
         (generic) — the stricter classification wins.
      3. First-class name match.
      4. Generic name match.
      5. Fall back to `RoomTier.hidden` — the safe default when nothing
         matches. The picker won't show the room; designer can edit later.

    Matching is case-insensitive substring. `RoomType.unknown` is treated
    as "no type signal" so the name pass runs.
    """
    if room_type != RoomType.unknown and room_type in _TYPE_TO_TIER:
        return _TYPE_TO_TIER[room_type]

    lower = name.lower()
    if any(hint in lower for hint in _HIDDEN_NAME_HINTS):
        return RoomTier.hidden
    if any(hint in lower for hint in _FIRST_CLASS_NAME_HINTS):
        return RoomTier.first_class
    if any(hint in lower for hint in _GENERIC_NAME_HINTS):
        return RoomTier.generic
    return RoomTier.hidden
