"""Structural-tier scorer: compares a parsed Project against a GoldenSpec.

Per the design doc §1.1, the structural tier should hold at ~100% — these are
the failures a designer catches at a glance ("you missed the master bedroom",
"two rooms overlap", "no staircase"). One error here and trust collapses.

Tier 1 checks here:
- All non-optional expected rooms are present (matched by name + floor)
- No extra rooms beyond what's expected (with `optional` rooms excused)
- Room type matches expectation
- No significant polygon overlaps within the same floor
- At least N staircases detected (per the golden's `expected_staircases_min`)

Dimensional + entity-recall tiers are deferred; add when needed.
"""

from dataclasses import dataclass
from enum import StrEnum

from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.eval.golden import GoldenSpec
from lighting_engine.models.geometry import Project, RoomType

# Two same-floor rooms are flagged as overlapping if the overlap area exceeds
# this threshold (sqm). 0.5 sqm catches meaningful overlaps without false-firing
# on shared-boundary nuances.
_OVERLAP_MIN_SQM = 0.5


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


@dataclass
class EvalIssue:
    severity: Severity
    category: str
    description: str


@dataclass
class TierScore:
    score: float          # 0.0 – 1.0
    passes: int
    total: int
    issues: list[EvalIssue]


@dataclass
class EvalResult:
    file: str
    structural: TierScore

    def passes_ci_gate(self, min_structural_score: float = 0.95) -> bool:
        return self.structural.score >= min_structural_score


def score_structural(project: Project, golden: GoldenSpec) -> TierScore:
    """Grade a Project against the golden spec on structural correctness."""
    issues: list[EvalIssue] = []
    passes = 0
    total = 0

    actual_by_key = {(r.floor_level, r.name): r for r in project.rooms}
    expected_by_key = {(g.floor_level, g.name): g for g in golden.expected_rooms}

    # 1. Required expected rooms present
    for key, expected in expected_by_key.items():
        if expected.optional:
            continue
        total += 1
        if key in actual_by_key:
            passes += 1
        else:
            floor, name = key
            issues.append(EvalIssue(
                severity=Severity.high,
                category="missing_room",
                description=f"Expected room {name!r} on floor {floor} not parsed",
            ))

    # 2. Type accuracy for matched rooms
    for key, expected in expected_by_key.items():
        actual = actual_by_key.get(key)
        if actual is None:
            continue
        total += 1
        if actual.type == expected.type:
            passes += 1
        else:
            floor, name = key
            issues.append(EvalIssue(
                severity=Severity.medium,
                category="type_mismatch",
                description=(
                    f"Room {name!r} on floor {floor}: expected type "
                    f"{expected.type.value}, got {actual.type.value}"
                ),
            ))

    # 3. Extra rooms (parsed but not in golden, ignoring shafts/optional names)
    optional_names = {(g.floor_level, g.name) for g in golden.expected_rooms if g.optional}
    for key in actual_by_key:
        # Treat duplicates of optional names as allowed (e.g. multiple SHAFTs)
        if key in optional_names:
            continue
        total += 1
        if key in expected_by_key:
            passes += 1
        else:
            floor, name = key
            issues.append(EvalIssue(
                severity=Severity.medium,
                category="extra_room",
                description=(
                    f"Parsed room {name!r} on floor {floor} not in golden — "
                    "either spurious or the golden needs updating"
                ),
            ))

    # 4. No same-floor polygon overlaps
    if golden.require_no_overlaps:
        total += 1
        overlaps_found = 0
        polys = [
            (r, ShapelyPolygon([(p.x, p.y) for p in r.polygon]))
            for r in project.rooms
        ]
        for i, (r1, p1) in enumerate(polys):
            for r2, p2 in polys[i + 1:]:
                if r1.floor_level != r2.floor_level:
                    continue
                if not p1.is_valid or not p2.is_valid:
                    continue
                if not p1.intersects(p2):
                    continue
                # Staircases sit *inside* other rooms architecturally
                # (the lobby contains the staircase, the foyer wraps it, etc.).
                # A staircase-vs-other-room overlap is semantically correct;
                # only flag staircase-vs-staircase (which would mean two stairs
                # at the same location — a real bug).
                is_stair_1 = r1.type == RoomType.staircase
                is_stair_2 = r2.type == RoomType.staircase
                if is_stair_1 ^ is_stair_2:
                    continue
                inter = p1.intersection(p2)
                if inter.area > _OVERLAP_MIN_SQM:
                    overlaps_found += 1
                    issues.append(EvalIssue(
                        severity=Severity.high,
                        category="overlap",
                        description=(
                            f"{r1.name!r} overlaps {r2.name!r} on floor "
                            f"{r1.floor_level} by {inter.area:.1f} sqm"
                        ),
                    ))
        if overlaps_found == 0:
            passes += 1

    # 5. Staircase count
    if golden.expected_staircases_min > 0:
        total += 1
        staircase_count = sum(
            1 for r in project.rooms if r.type == RoomType.staircase
        )
        if staircase_count >= golden.expected_staircases_min:
            passes += 1
        else:
            issues.append(EvalIssue(
                severity=Severity.high,
                category="missing_staircases",
                description=(
                    f"Expected ≥{golden.expected_staircases_min} staircase(s), "
                    f"found {staircase_count}"
                ),
            ))

    score = passes / total if total > 0 else 1.0
    return TierScore(score=score, passes=passes, total=total, issues=issues)
