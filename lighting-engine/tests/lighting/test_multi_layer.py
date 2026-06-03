from lighting_engine.brief.models import (
    FixturePreference,
    LightingLayer,
    RoomBrief,
    Zone,
)
from lighting_engine.digest import compute_digest
from lighting_engine.digest.models import RoomDigest
from lighting_engine.lighting.multi_layer import compute_all_fixtures
from lighting_engine.models.geometry import (
    LightingLayer as IRLayer,
)
from lighting_engine.models.geometry import (
    Point,
    Project,
    Room,
    RoomType,
)


def _dining_room() -> tuple[Room, RoomDigest]:
    room = Room(
        id="dr",
        name="DINING",
        type=RoomType.dining,
        floor_level=0,
        polygon=[
            Point(x=0, y=0),
            Point(x=5, y=0),
            Point(x=5, y=4),
            Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
    )
    digest = compute_digest(Project(id="p", name="x", rooms=[room])).rooms[0]
    return room, digest


def test_multi_layer_dispatches_each_layer_to_its_module() -> None:
    room, digest = _dining_room()
    brief = RoomBrief(
        target_lux_ambient=200.0,
        cct_main=2700,
        fixture_preference=FixturePreference.warm_bias,
        layers_needed=[
            LightingLayer.ambient,
            LightingLayer.task,
            LightingLayer.decorative,
        ],
        zones=[
            Zone(
                layer=LightingLayer.ambient,
                purpose="ambient",
                cct_k=2700,
                cri_min=90,
                fixture_type="downlight",
                position_hint="center",
            ),
            Zone(
                layer=LightingLayer.task,
                purpose="task above table",
                cct_k=2700,
                cri_min=90,
                fixture_type="pendant",
                position_hint="above dining table",
            ),
            Zone(
                layer=LightingLayer.decorative,
                purpose="chandelier",
                cct_k=2700,
                cri_min=90,
                fixture_type="chandelier",
                position_hint="center",
            ),
        ],
        warnings=[],
        design_rationale="evening dining",
        design_notes=[],
        floor_lamp_suggestions=[],
        table_lamp_suggestions=[],
    )
    fixtures = compute_all_fixtures(room, digest, brief)
    by_layer: dict[IRLayer, list[object]] = {
        layer: [f for f in fixtures if f.layer == layer]
        for layer in (IRLayer.ambient, IRLayer.task, IRLayer.decorative)
    }
    assert by_layer[IRLayer.ambient]
    assert by_layer[IRLayer.task]
    assert by_layer[IRLayer.decorative]
    # ambient grid has several downlights, task has 1, decorative has 1
    assert len(by_layer[IRLayer.task]) == 1
    assert len(by_layer[IRLayer.decorative]) == 1
    assert len(by_layer[IRLayer.ambient]) >= 2


def test_multi_layer_handles_empty_brief_zones() -> None:
    room, digest = _dining_room()
    # RoomBrief enforces zones min_length=1 + layers_needed min_length=1, so
    # an empty-zones brief is impossible by construction. Instead we test
    # that a brief whose only zone is a layer the orchestrator can't place
    # (ambient on a room type the standards table opts out of would also do
    # it, but no such room type currently exists). We use a brief with a
    # single ambient zone on a foyer-shaped room… but the simpler check is:
    # if a brief has zero non-ambient zones and ambient fires once, total
    # is at least 1 — i.e. the orchestrator doesn't crash on a minimal brief.
    brief = RoomBrief(
        target_lux_ambient=200.0,
        cct_main=2700,
        fixture_preference=FixturePreference.warm_bias,
        layers_needed=[LightingLayer.ambient],
        zones=[
            Zone(
                layer=LightingLayer.ambient,
                purpose="ambient only",
                cct_k=2700,
                cri_min=90,
                fixture_type="downlight",
                position_hint="center",
            ),
        ],
        warnings=[],
        design_rationale="ambient only",
        design_notes=[],
        floor_lamp_suggestions=[],
        table_lamp_suggestions=[],
    )
    fixtures = compute_all_fixtures(room, digest, brief)
    # Ambient placement always fires for dining rooms; ensure orchestrator
    # produced fixtures and they are all on the ambient layer.
    assert len(fixtures) >= 1
    assert all(f.layer == IRLayer.ambient for f in fixtures)


def test_multi_layer_collapses_duplicate_ambient_zones() -> None:
    """Two ambient zones in a brief still produce only one ambient grid pass."""
    room, digest = _dining_room()
    brief = RoomBrief(
        target_lux_ambient=200.0,
        cct_main=2700,
        fixture_preference=FixturePreference.warm_bias,
        layers_needed=[LightingLayer.ambient],
        zones=[
            Zone(
                layer=LightingLayer.ambient,
                purpose="ambient general",
                cct_k=2700,
                cri_min=90,
                fixture_type="downlight",
                position_hint="center",
            ),
            Zone(
                layer=LightingLayer.ambient,
                purpose="ambient duplicate",
                cct_k=2700,
                cri_min=90,
                fixture_type="downlight",
                position_hint="center",
            ),
        ],
        warnings=[],
        design_rationale="duplicate ambient",
        design_notes=[],
        floor_lamp_suggestions=[],
        table_lamp_suggestions=[],
    )
    fixtures = compute_all_fixtures(room, digest, brief)
    # Grid count is deterministic from room area, so two ambient zones must
    # not double it.
    ambient_count = sum(1 for f in fixtures if f.layer == IRLayer.ambient)
    # Compute the expected single-pass count.
    from lighting_engine.lighting.placement import compute_ambient_layer
    expected = len(compute_ambient_layer(room, digest))
    assert ambient_count == expected
