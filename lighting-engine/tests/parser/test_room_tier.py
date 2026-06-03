"""Tests for the room-tier classifier (spec §3.1)."""

from pathlib import Path

import pytest

from lighting_engine.models.geometry import RoomTier, RoomType
from lighting_engine.parser.pipeline import parse_file
from lighting_engine.parser.room_tier import classify_room_tier

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"


# --- Synthetic: every RoomType maps to the spec's tier --------------------


@pytest.mark.parametrize(
    "room_type, expected_tier",
    [
        (RoomType.living, RoomTier.first_class),
        (RoomType.dining, RoomTier.first_class),
        (RoomType.bedroom, RoomTier.first_class),
        (RoomType.kitchen, RoomTier.first_class),
        (RoomType.study, RoomTier.first_class),
        (RoomType.foyer, RoomTier.generic),
        (RoomType.hallway, RoomTier.generic),
        (RoomType.bathroom, RoomTier.hidden),
        (RoomType.staircase, RoomTier.hidden),
        (RoomType.outdoor, RoomTier.hidden),
    ],
)
def test_room_type_maps_to_spec_tier(
    room_type: RoomType, expected_tier: RoomTier,
) -> None:
    """Every RoomType (except `unknown`) classifies via the type map alone.

    The `name` argument is empty so any name-substring fallback won't muddy
    the result — this exercises the type-only path.
    """
    assert classify_room_tier(room_type, "") == expected_tier


def test_unknown_type_defaults_hidden_when_name_has_no_hints() -> None:
    """`RoomType.unknown` + an unhinted name returns hidden — the safe
    default that keeps unclassified rooms out of the v1 picker."""
    assert classify_room_tier(RoomType.unknown, "Room 42") == RoomTier.hidden


# --- Synthetic: name-substring fallback for Indian residential vocab ------


@pytest.mark.parametrize(
    "name",
    [
        "DRAWING ROOM",
        "FORMAL LIVING",
        "FAMILY LOUNGE",
        "MASTER BEDROOM",
        "GUEST BEDROOM",
        "BAR",
        "STUDY ROOM",
        "WFH ROOM",
        "PUJA ROOM",
    ],
)
def test_name_matching_recovers_first_class_when_type_unknown(name: str) -> None:
    """For ambiguous RoomType.unknown cases, the case-insensitive name
    fallback must catch first-class Indian-residential vocab the
    `RoomType` enum doesn't cover (DRAWING, PUJA, FAMILY LOUNGE, BAR).
    """
    assert classify_room_tier(RoomType.unknown, name) == RoomTier.first_class
    assert classify_room_tier(RoomType.unknown, name.lower()) == RoomTier.first_class


@pytest.mark.parametrize(
    "name",
    ["FOYER", "ENTRANCE FOYER", "LOBBY", "PASSAGE", "DRESS", "MASTER DRESS"],
)
def test_name_matching_recovers_generic_when_type_unknown(name: str) -> None:
    assert classify_room_tier(RoomType.unknown, name) == RoomTier.generic


@pytest.mark.parametrize(
    "name",
    [
        "TOILET",
        "MASTER TOILET",
        "BATHROOM",
        "STORAGE",
        "STORE ROOM",
        "UTILITY ROOM",
        "WASHING AREA",
        "COURTYARD",
        "TERRACE",
        "STAIRCASE",
        "BALCONY",
        "SHAFT",
    ],
)
def test_name_matching_recovers_hidden_when_type_unknown(name: str) -> None:
    assert classify_room_tier(RoomType.unknown, name) == RoomTier.hidden


def test_hidden_name_wins_over_first_class_when_both_match() -> None:
    """If a name accidentally contains both a hidden hint and a first-class
    hint (e.g. "BAR STORAGE" or "KITCHEN STORAGE"), hidden takes priority.
    Storage is a service space regardless of which habitable room it
    serves; the stricter classification wins."""
    assert classify_room_tier(RoomType.unknown, "BAR STORAGE") == RoomTier.hidden
    assert (
        classify_room_tier(RoomType.unknown, "KITCHEN STORAGE")
        == RoomTier.hidden
    )


def test_type_match_beats_name_match() -> None:
    """When RoomType is set (not unknown), the type-driven tier wins even if
    the name suggests a different tier. The parser already chose a type;
    trust it."""
    # A "BEDROOM" room mistakenly typed as `bathroom` stays hidden.
    assert (
        classify_room_tier(RoomType.bathroom, "MASTER BEDROOM") == RoomTier.hidden
    )


# --- Delhi fixture: real-world coverage ----------------------------------


def test_delhi_fixture_classifies_at_least_six_first_class_rooms() -> None:
    """The real Delhi DWG should produce at least 6 first-class rooms.

    Habitable spaces in the Mohak residence include DRAWING ROOM, DINING,
    KITCHEN, BAR, FAMILY LOUNGE, PUJA ROOM, MASTER BEDROOM, GUEST BEDROOM,
    BEDROOM-1, BEDROOM-2, STUDY ROOM — at least 6 of which should reach
    first-class even if a couple slip through as `unknown` with names the
    fallback doesn't catch."""
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="x",
    )
    first_class = [r for r in project.rooms if r.tier == RoomTier.first_class]
    first_class_names = sorted({r.name for r in first_class})
    assert len(first_class) >= 6, (
        f"Expected ≥6 first-class rooms; got {len(first_class)}: "
        f"{first_class_names}"
    )
    # Spot-check the bedrooms / drawing room are caught.
    upper_names = {n.upper() for n in first_class_names}
    expected_present = {"DRAWING ROOM", "MASTER BEDROOM", "KITCHEN"}
    missing = expected_present - upper_names
    assert not missing, f"Missing expected first-class rooms: {missing}"


def test_delhi_fixture_toilets_and_storage_classify_as_hidden() -> None:
    """Hidden-tier rooms in the Delhi fixture: every TOILET / STORAGE /
    BATH variant must end up as `hidden` so the picker doesn't show them.
    """
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="x",
    )
    hidden_keywords = ("TOILET", "STORAGE", "STORE", "BATH")
    hidden_rooms = [
        r for r in project.rooms
        if any(kw in r.name.upper() for kw in hidden_keywords)
    ]
    assert hidden_rooms, "Delhi fixture should have at least one toilet/storage room"
    for r in hidden_rooms:
        assert r.tier == RoomTier.hidden, (
            f"{r.name} ({r.type}) classified as {r.tier}, expected hidden"
        )
