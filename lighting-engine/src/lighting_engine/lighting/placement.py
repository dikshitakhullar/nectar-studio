"""Orchestrator: room digest → ambient downlight Fixtures.

Pure code, no LLM. Reads a RoomDigest, consults the typed standards table,
picks a default fixture, runs the lumen method to size the count, and lays
out the grid.

Output: `Fixture` objects appended to the room's `existing_fixtures` list
with `source="proposed"` and `layer="ambient"`. The architect's parsed
fixtures stay in place (`source="parsed"`) — they're not mutated.
"""

from lighting_engine.digest import RoomDigest
from lighting_engine.lighting.fixtures import FixtureSpec, pick_default_fixture
from lighting_engine.lighting.grid import compute_ambient_grid
from lighting_engine.lighting.lumen_method import (
    fixture_count_for_room,
    required_lumens,
    spacing_m,
)
from lighting_engine.lighting.standards import LuxStandard, get_lux_standard
from lighting_engine.models.geometry import (
    Fixture,
    FixtureSource,
    LightingLayer,
    Room,
    RoomType,
)


def compute_ambient_layer(
    room: Room,
    digest: RoomDigest,
    *,
    override_fixture: FixtureSpec | None = None,
) -> list[Fixture]:
    """Compute proposed ambient fixtures for one room.

    Returns an empty list for room types that don't get ambient downlights in
    v0 (outdoor, staircase, or anything with `place_ambient=False` in the
    standards table).

    `override_fixture` lets callers pin a specific FixtureSpec (e.g. tests, or
    a future brief-driven selection). When `None`, we pick warm vs cool by the
    room type's preferred CCT.
    """
    standard = get_lux_standard(room.type)
    if not standard.place_ambient or digest.area_sqm <= 0:
        return []

    spec = override_fixture or pick_default_fixture(room.type, standard)
    count = fixture_count_for_room(
        standard.target_lux, digest.area_sqm, spec.lumens,
    )
    if count <= 0:
        return []

    max_spacing = spacing_m(spec.s_mh_ratio, digest.ceiling_height_m)
    positions = compute_ambient_grid(
        room.polygon, count, max_spacing_m=max_spacing,
    )
    if not positions:
        return []

    reasoning = _reasoning_for(room.type, standard, spec, count, digest)
    return [
        Fixture(
            id=f"{room.id}-amb-{i:03d}",
            type="downlight",
            position=pos,
            source=FixtureSource.proposed,
            layer=LightingLayer.ambient,
            reasoning=reasoning,
            wattage_w=spec.wattage_w,
            lumens=spec.lumens,
            cct_k=spec.cct_k,
            cri=spec.cri,
            beam_angle_deg=spec.beam_angle_deg,
        )
        for i, pos in enumerate(positions)
    ]


def _reasoning_for(
    room_type: RoomType,
    standard: LuxStandard,
    spec: FixtureSpec,
    count: int,
    digest: RoomDigest,
) -> str:
    """Plain-English rationale string the report can quote verbatim."""
    needed = required_lumens(standard.target_lux, digest.area_sqm)
    return (
        f"Ambient fill for {room_type.value} — target {standard.target_lux} lux "
        f"× {digest.area_sqm:.1f} sqm ≈ {needed:.0f} lm needed "
        f"(UF 0.6, MF 0.8). {count} × {spec.wattage_w:.0f}W "
        f"{spec.cct_k}K CRI{spec.cri} downlights "
        f"({spec.lumens:.0f} lm each) on a {spec.s_mh_ratio}×MH grid."
    )


def place_ambient_for_project(
    rooms: list[Room],
    digests: list[RoomDigest],
) -> dict[str, list[Fixture]]:
    """Run ambient placement for every room in a project, keyed by room id."""
    by_id = {d.room_id: d for d in digests}
    out: dict[str, list[Fixture]] = {}
    for room in rooms:
        digest = by_id.get(room.id)
        if digest is None:
            continue
        out[room.id] = compute_ambient_layer(room, digest)
    return out
