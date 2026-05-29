# nectar-studio

AI lighting design tooling for residential interior designers.

The first product surface is a **lighting prescription audit**: designer uploads a DWG of the project + a short brief, gets back a downloadable PDF report with functional-layer prescription, IES compliance check, daylight context, decorative advisory, and pre-install warnings. Replaces the multi-day vendor lux loop for projects without a dedicated lighting consultant.

## Repo layout

- `lighting-engine/` — Python service: DWG/DXF parsing, geometry model, rule library (YAML), lighting math, daylight model, prescription engine, JSON output
- `web/` — Next.js web app (Plan B, not yet built): upload + brief UI + report view + PDF generation
- `docs/` — local-only (gitignored): strategy, specs, plans, research

## Design + plans

Local-only at:

- `docs/superpowers/specs/2026-05-28-lighting-prescription-mvp-design.md` — MVP design spec
- `docs/superpowers/plans/2026-05-28-lighting-engine-mvp.md` — engine implementation plan
- `docs/superpowers/specs/2026-05-23-ai-lighting-consultant-agent-design.md` — broader vision (full Lighting Pack)
- `docs/research/lighting/` — 7-day curriculum + engine reference rules
- `docs/research/interior-designer-call-2.md` — source pain notes

## Origin

Spun out of nectar-viz (the consumer-facing visualizer at `~/Desktop/nectar-viz`). Different audience (B2B designers vs. consumers + designers), different stack (Python engine vs. Next.js + Gemini rendering), different deployment, different sales motion. Kept as a separate repo for clean history and dependency isolation.
