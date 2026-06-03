"""FastAPI service for the lighting-engine.

Phase 2 (per docs/superpowers/specs/2026-06-03-v1-design.md) — exposes the
HTTP contract the Next.js studio frontend calls. Routes, SQLite persistence
and a stubbed generation pipeline live here; phases 3-6 will replace the
stub with the real LLM brief + placement + lux + SVG pipeline.
"""

from lighting_engine.api.app import app

__all__ = ["app"]
