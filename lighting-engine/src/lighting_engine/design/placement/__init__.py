"""Placement rule library — converts each LightingZone into Fixtures.

Each intent has its own placement rule (in `rules.py`). The orchestrator
in `orchestrator.py` dispatches by intent, applies hard constraints from
`hard_rules.py`, and returns the merged Fixture list ready for rendering.
"""

from lighting_engine.design.placement.orchestrator import place_design

__all__ = ["place_design"]
