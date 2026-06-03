# nectar-studio — frontend

Next.js 16 app that wraps the lighting-engine FastAPI service. Built for the
v1 designer demo flow: upload DWG → pick room → confirm → generate → view plan.

## Local dev

```bash
# Terminal 1 — engine
cd ../lighting-engine
uv run uvicorn lighting_engine.api.app:app --reload --port 8000

# Terminal 2 — studio
cd studio
npm install
cp .env.local.example .env.local  # optional — defaults work
npm run dev
open http://localhost:3000/studio/upload
```

## Architecture

- `app/studio/` — one folder per page, all client components.
- `lib/api/client.ts` — single typed client; **never** call `fetch` directly
  from page components.
- `lib/api/types.ts` — hand-maintained TS mirror of `shared/openapi.yaml`.
  When the engine contract changes, regenerate with
  `cd ../lighting-engine && uv run python scripts/export_openapi.py`, then
  update this file by hand to match. (We hand-write rather than codegen to
  keep the file readable in PR reviews; v1.1 may swap to
  `openapi-typescript`.)
- `lib/api/url-state.ts` — `pid` + `rid` flow through `?pid=…&rid=…` query
  params. No global state library.

## Conventions

- TypeScript strict mode; no `any`.
- Tailwind for styling — cream backgrounds, stone palette, amber accents.
- Loading states use `<Spinner>` from `components/UIPrimitives`.
- Errors surface via `ApiError` (preserves HTTP status + parsed FastAPI
  `detail`) and render via `<ErrorBanner>` with optional retry.
