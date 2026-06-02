"""Eval-harness CI gate: the parser must hold structural correctness on the
real Delhi DWG above a threshold. This catches regressions like the multi-sheet
duplication, room overlap, or wholesale rooms-disappearing bugs we've already
hit during development.

The threshold starts permissive (it ratchets up as we improve the parser):
- 80% structural score for now (we have known gaps — staircase detection,
  some over-clipping). Bump as those land.
"""

from pathlib import Path

from lighting_engine.eval import load_golden, score_structural
from lighting_engine.parser.pipeline import parse_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "dwgs"
GOLDEN = Path(__file__).parent / "golden"

# Current realistic baseline. Raise this as parser improves (especially after
# staircase detection and edge-case position fixes).
_STRUCTURAL_FLOOR = 0.80


def test_real_base_architectural_structural_score():
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="Mohak Residence",
    )
    golden = load_golden(GOLDEN / "real_base_architectural.yaml")
    result = score_structural(project, golden)

    # Print the issues so failing CI shows what's wrong without forcing -v
    if result.score < _STRUCTURAL_FLOOR:
        print(f"\n=== Structural score {result.score:.2%} below floor {_STRUCTURAL_FLOOR:.0%} ===")
        for issue in result.issues:
            print(f"  [{issue.severity.value:<6}] {issue.category}: {issue.description}")

    assert result.score >= _STRUCTURAL_FLOOR, (
        f"Structural score {result.score:.2%} ({result.passes}/{result.total}) "
        f"below floor {_STRUCTURAL_FLOOR:.0%}"
    )


def test_real_base_architectural_no_missing_required_rooms():
    """Tighter check: no expected non-optional room should be missing."""
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="x",
    )
    golden = load_golden(GOLDEN / "real_base_architectural.yaml")
    result = score_structural(project, golden)

    missing = [i for i in result.issues if i.category == "missing_room"]
    assert not missing, "\n".join(
        f"  - {i.description}" for i in missing
    )


def test_real_base_architectural_overlaps_do_not_regress():
    """Ratchet: the parser currently produces 11 same-floor polygon overlaps
    totaling ~92 sqm (most in the open-plan drawing/foyer/courtyard area, and
    a few from windowless rooms with bad anchoring). This test gates on the
    COUNT — it fails if we regress (new overlaps introduced) and is meant to
    be ratcheted DOWN as we fix the underlying rooms (drag-to-fix UI in Chunk
    3, better anchoring logic, etc.).

    When you fix an overlap, *lower these baselines*. That's the ratchet."""
    project, _ = parse_file(
        FIXTURES / "real_base_architectural.dxf",
        project_name="x",
    )
    golden = load_golden(GOLDEN / "real_base_architectural.yaml")
    result = score_structural(project, golden)

    overlaps = [i for i in result.issues if i.category == "overlap"]

    # Current baseline as of 2026-06-02. LOWER these when overlaps are fixed.
    max_overlap_count = 11

    if len(overlaps) > max_overlap_count:
        # Regression — show what's new
        lines = "\n".join(f"  - {i.description}" for i in overlaps)
        raise AssertionError(
            f"Overlap count regressed: {len(overlaps)} > baseline "
            f"{max_overlap_count}. Current overlaps:\n{lines}"
        )
