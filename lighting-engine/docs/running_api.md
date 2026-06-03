# Running the lighting-engine FastAPI service

## Local dev

```
uv sync
uv run uvicorn lighting_engine.api.app:app --reload --port 8000
open http://localhost:8000/docs
```

SQLite state lives in `lighting-engine/data/state.db`. Uploaded DWG/DXF files
are persisted under `lighting-engine/data/projects/{project_id}/`. Both
directories are created on first request; safe to delete to reset state.

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `LIGHTING_ENGINE_DB_URL` | `sqlite+aiosqlite:///data/state.db` | SQLAlchemy URL. Tests set this per-run. |
| `LIGHTING_ENGINE_PROJECTS_DIR` | `data/projects/` | Upload storage root. |
| `CORS_ALLOWED_ORIGINS` | (empty) | Comma-separated extra origins on top of `http://localhost:3000` and `https://*.vercel.app`. |

## Export OpenAPI

```
uv run python scripts/export_openapi.py
# → writes shared/openapi.yaml
```

The studio uses this YAML to regenerate its TypeScript client. Run as part of
CI on any change to `src/lighting_engine/api/`.

## Tests

```
uv run pytest tests/api/ -v
```

Each test gets an isolated SQLite file in pytest's `tmp_path` so runs don't
share state.
