# lighting-engine

Python MVP engine for residential lighting prescription. Takes a DWG/DXF + JSON brief, returns a JSON analysis.

See `docs/superpowers/specs/2026-05-28-lighting-prescription-mvp-design.md` for the design.

## Quick start

    uv sync
    uv run python -m lighting_engine path/to/plan.dwg path/to/brief.json
