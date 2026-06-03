# Reference material — not active code

Everything under this directory is **reference**, not built or shipped. It lives here so future conversations have the same context the original prototype work was built against.

## `studio-prototype/`

The clickable UX prototype of the "Lighting Studio" product, originally developed inside the `nectar-viz` repo on the `studio-prototype-phase0` branch (~93 commits, May 2026). Stays here as a UX reference for when the Plan B Next.js web wrapper gets built — many components, layouts, scene-programming patterns, fixture-schedule rendering, art-lighting comparisons, and brand identity choices were worked out in this prototype.

- **`app/`** — Next.js App Router pages (routes: `/studio`, `/studio/upload`, `/studio/project-profile`, `/studio/walls`, `/studio/pack`, `/studio/art-lighting`, `/studio/brief`, `/studio/generating`, `/studio/landing-options`, `/studio/agent-options`, etc.). Plus shared `components/` (LightingTip, room renders, scene controls, etc.).
- **`public/`** — illustrations, agent portraits, render samples, landing options, art-lighting demo images.

The prototype was built to demo the full vision (the May 23 Lighting Pack spec). **The actual MVP we're shipping is narrower** — see `docs/superpowers/specs/2026-05-28-lighting-prescription-mvp-design.md`. The prototype is most useful for:

- Brand identity / aesthetic (dark luxury editorial — though the production PDF report uses a clean light theme per the MVP spec §8.4)
- Component patterns we'll port to Plan B (web wrapper) when it ships
- Scene programming UI patterns
- Wall elevation / RCP rendering patterns
- Iteration chat panel pattern
- Fixture schedule table styling

**Do not build or run the prototype here** — it depends on the parent nectar-viz Next.js setup (different package.json, brand assets shared with the consumer visualizer, etc.). Open files for browsing only.

## Origin

The parent `nectar-viz` project lives at `~/Desktop/nectar-viz` and remains the consumer-facing visualizer (Browse + AI Pick + Visual Search). `nectar-studio` was spun off because the audience (B2B designers), stack (Python engine + Next.js wrapper), and sales motion differ enough to warrant a separate codebase.
