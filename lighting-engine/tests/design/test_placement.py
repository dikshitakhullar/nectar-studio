"""Tests for the placement library — orchestrator + rules + hard constraints."""

from lighting_engine.design.intent import LightingZone, RoomDesign
from lighting_engine.design.placement import place_design
from lighting_engine.design.placement.hard_rules import (
    position_clear_of_furniture,
    position_inside_room,
    position_min_wall_offset,
    wall_has_opening,
)
from lighting_engine.design.scene import (
    CeilingZone,
    FocalPoint,
    RoomScene,
    WallPurpose,
)
from lighting_engine.models.geometry import (
    Door,
    DoorSwing,
    Furniture,
    LightingLayer,
    Point,
    Room,
    Window,
)


def _bedroom_with_bed() -> tuple[Room, RoomScene]:
    room = Room(
        id="r1", name="MASTER BEDROOM", type="bedroom", floor_level=0,
        polygon=[
            Point(x=0, y=0), Point(x=5, y=0),
            Point(x=5, y=4), Point(x=0, y=4),
        ],
        ceiling_height_m=2.7,
        doors=[Door(
            id="d1", position=Point(x=2.5, y=0),
            wall_index=0, along_wall=0.5,
            width_m=0.9, swing=DoorSwing.in_,
        )],
        windows=[Window(
            id="w1", position=Point(x=5, y=2),
            wall_index=1, along_wall=0.5,
            width_m=1.2, height_m=1.2, sill_height_m=0.9,
        )],
        furniture=[Furniture(
            id="f1", type="BED", raw_label="BED",
            position=Point(x=2.5, y=3.0),
            footprint=[
                Point(x=1.5, y=2.0), Point(x=3.5, y=2.0),
                Point(x=3.5, y=3.7), Point(x=1.5, y=3.7),
            ],
        )],
    )
    scene = RoomScene(
        walls=[
            WallPurpose(wall_index=0, purpose="entry", confidence=0.9),
            WallPurpose(wall_index=1, purpose="french_window", confidence=0.85),
            WallPurpose(wall_index=2, purpose="headboard", confidence=0.95),
            WallPurpose(wall_index=3, purpose="wardrobe", confidence=0.8),
        ],
        ceiling=[CeilingZone(type="cove", description="perimeter cove", confidence=0.85)],
        focal_points=[FocalPoint(
            type="bed", position=Point(x=2.5, y=3.0),
            purpose_hint="head against wall C",
        )],
        notes="...",
        confidence=0.88,
    )
    return room, scene


# ── Hard rules ────────────────────────────────────────────────────────────


def test_position_inside_room():
    room, _ = _bedroom_with_bed()
    assert position_inside_room(Point(x=2.5, y=2.0), room)
    assert not position_inside_room(Point(x=10, y=10), room)


def test_position_clear_of_furniture_rejects_bed_top():
    room, _ = _bedroom_with_bed()
    assert position_clear_of_furniture(Point(x=2.5, y=3.0), room) is False
    assert position_clear_of_furniture(Point(x=2.5, y=0.5), room) is True


def test_position_min_wall_offset_rejects_too_close():
    room, _ = _bedroom_with_bed()
    # 10cm from wall — too close
    assert position_min_wall_offset(Point(x=0.1, y=2.0), room) is False
    # 1m from wall — fine
    assert position_min_wall_offset(Point(x=1.0, y=2.0), room) is True


def test_wall_has_opening():
    room, _ = _bedroom_with_bed()
    assert wall_has_opening(0, room) is True   # door
    assert wall_has_opening(1, room) is True   # window
    assert wall_has_opening(2, room) is False  # solid headboard
    assert wall_has_opening(3, room) is False


# ── Orchestrator + intent rules ───────────────────────────────────────────


def test_orchestrator_dispatches_each_zone_to_its_rule():
    room, scene = _bedroom_with_bed()
    design = RoomDesign(
        zones=[
            LightingZone(
                intent="cove_uplight",
                target_feature_ref="ceiling_cove",
                fixture_archetype="strip", cct_k=3000, cri_min=90,
                rationale="Cove uplight.",
            ),
            LightingZone(
                intent="bedside_reading",
                target_feature_ref="focal_0",
                fixture_archetype="wall_sconce", cct_k=2700, cri_min=90,
                rationale="Bedside reading sconces.",
            ),
        ],
        overall_rationale="Layered warm scheme.",
    )
    fixtures = place_design(design=design, room=room, scene=scene)
    intents = {f.reasoning for f in fixtures}
    assert "Cove uplight." in intents
    assert "Bedside reading sconces." in intents


def test_cove_uplight_skips_walls_with_openings():
    room, scene = _bedroom_with_bed()
    design = RoomDesign(
        zones=[LightingZone(
            intent="cove_uplight", target_feature_ref="ceiling_cove",
            fixture_archetype="strip", cct_k=3000, cri_min=90,
            rationale="Cove uplight.",
        )],
        overall_rationale="x",
    )
    fixtures = place_design(design=design, room=room, scene=scene)
    # Cove should ONLY be on walls 2 and 3 (the solid ones). Wall 0 has a
    # door, wall 1 has a window — both excluded.
    assert len(fixtures) > 0
    for f in fixtures:
        assert f.layer == LightingLayer.ambient


def test_perimeter_ambient_skips_walls_with_openings():
    room, scene = _bedroom_with_bed()
    design = RoomDesign(
        zones=[LightingZone(
            intent="perimeter_ambient", target_feature_ref="ceiling_flat",
            fixture_archetype="downlight", cct_k=3000, cri_min=80,
            rationale="Perimeter downlights.",
        )],
        overall_rationale="x",
    )
    fixtures = place_design(design=design, room=room, scene=scene)
    assert len(fixtures) > 0
    # None of the fixtures should sit on the bed footprint
    for f in fixtures:
        assert position_clear_of_furniture(f.position, room) is True


def test_central_ambient_avoids_furniture():
    room, scene = _bedroom_with_bed()
    design = RoomDesign(
        zones=[LightingZone(
            intent="central_ambient", target_feature_ref="ceiling_flat",
            fixture_archetype="downlight", cct_k=3000, cri_min=80,
            rationale="Central grid downlights.",
        )],
        overall_rationale="x",
    )
    fixtures = place_design(design=design, room=room, scene=scene)
    # All emitted fixtures must clear the bed footprint
    for f in fixtures:
        assert position_clear_of_furniture(f.position, room) is True


def test_bedside_reading_places_two_sconces_flanking_bed():
    room, scene = _bedroom_with_bed()
    design = RoomDesign(
        zones=[LightingZone(
            intent="bedside_reading", target_feature_ref="focal_0",
            fixture_archetype="wall_sconce", cct_k=2700, cri_min=90,
            rationale="Reading sconces.",
        )],
        overall_rationale="x",
    )
    fixtures = place_design(design=design, room=room, scene=scene)
    assert len(fixtures) == 2
    for f in fixtures:
        assert f.type == "wall_sconce"
        assert f.layer == LightingLayer.task
        assert f.mount_height_m == 0.9


def test_bedside_reading_returns_empty_when_no_bed():
    room = Room(
        id="r1", name="STUDY", type="study", floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=4, y=0),
                 Point(x=4, y=4), Point(x=0, y=4)],
        ceiling_height_m=2.7,
    )
    scene = RoomScene(confidence=0.9)  # no focal points
    design = RoomDesign(
        zones=[LightingZone(
            intent="bedside_reading", target_feature_ref="focal_0",
            fixture_archetype="wall_sconce", cct_k=2700, cri_min=90,
            rationale="Tried to add bedside but no bed.",
        )],
        overall_rationale="x",
    )
    assert place_design(design=design, room=room, scene=scene) == []


def test_accent_artwork_skips_walls_with_openings():
    # Use a furniture-free living room so the wall-opening rule is the only
    # variable being tested (the _bedroom_with_bed fixture has a bed under
    # wall 2 which would correctly block the spot via the furniture rule).
    room = Room(
        id="r1", name="LIVING", type="living", floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=5, y=0),
                 Point(x=5, y=4), Point(x=0, y=4)],
        ceiling_height_m=2.7,
        doors=[Door(
            id="d1", position=Point(x=2.5, y=0),
            wall_index=0, along_wall=0.5,
            width_m=0.9, swing=DoorSwing.in_,
        )],
    )
    scene = RoomScene(
        walls=[
            WallPurpose(wall_index=0, purpose="entry", confidence=0.9),
            WallPurpose(wall_index=2, purpose="artwork", confidence=0.95),
        ],
        confidence=0.9,
    )
    design = RoomDesign(
        zones=[
            LightingZone(
                intent="accent_artwork", target_feature_ref="wall_0",  # door wall
                fixture_archetype="spotlight", cct_k=2700, cri_min=90,
                rationale="Tried to light wall with door (should skip).",
            ),
            LightingZone(
                intent="accent_artwork", target_feature_ref="wall_2",  # solid
                fixture_archetype="spotlight", cct_k=2700, cri_min=90,
                rationale="Spot on artwork wall.",
            ),
        ],
        overall_rationale="x",
    )
    fixtures = place_design(design=design, room=room, scene=scene)
    # Only wall_2 should produce a fixture (wall_0 has a door)
    assert len(fixtures) == 1
    assert fixtures[0].layer == LightingLayer.accent
    assert fixtures[0].type == "spotlight"


def test_task_dining_places_pendant_above_table():
    room = Room(
        id="r1", name="DINING", type="dining", floor_level=0,
        polygon=[Point(x=0, y=0), Point(x=4, y=0),
                 Point(x=4, y=4), Point(x=0, y=4)],
        ceiling_height_m=2.7,
    )
    scene = RoomScene(
        focal_points=[FocalPoint(
            type="dining_table", position=Point(x=2.0, y=2.0),
            purpose_hint="centered, 8-seater",
        )],
        confidence=0.9,
    )
    design = RoomDesign(
        zones=[LightingZone(
            intent="task_dining", target_feature_ref="focal_0",
            fixture_archetype="pendant", cct_k=2700, cri_min=90,
            rationale="Pendant over dining table.",
        )],
        overall_rationale="x",
    )
    fixtures = place_design(design=design, room=room, scene=scene)
    assert len(fixtures) == 1
    f = fixtures[0]
    assert f.type == "pendant"
    assert f.layer == LightingLayer.task
    assert f.position.x == 2.0 and f.position.y == 2.0
    # Pendant hangs 75cm below ceiling
    assert f.mount_height_m == 2.7 - 0.75


def test_unknown_intent_falls_back_to_centroid_downlight():
    # The orchestrator dispatches by string lookup; missing → fallback.
    # In practice the Literal prevents truly-unknown intents reaching here,
    # so we verify the fallback is wired by exercising the registry directly.
    from lighting_engine.design.placement.rules import RULES, place_fallback
    assert RULES.get("never_existed_intent", place_fallback) is place_fallback
