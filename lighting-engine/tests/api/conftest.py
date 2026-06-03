"""Test fixtures for the FastAPI service.

Each test gets:

* a fresh SQLite file in a tmp dir (overrides ``LIGHTING_ENGINE_DB_URL``)
* a fresh ``data/projects`` dir (overrides ``LIGHTING_ENGINE_PROJECTS_DIR``)
* a ``TestClient`` bound to the real ``app`` instance

Tests rely on the FastAPI lifespan + ``init_db`` to materialise the schema,
so the client must be entered via ``with TestClient(app) as client:`` (which
``client_factory`` handles).
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lighting_engine.api import db as db_module
from lighting_engine.api.routes import generation as generation_routes


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """A unique SQLite file per test; aiosqlite cannot reliably share an
    in-memory DB across the multiple connections FastAPI dependencies open."""
    return f"sqlite+aiosqlite:///{tmp_path / 'state.db'}"


@pytest.fixture
def tmp_projects_dir(tmp_path: Path) -> Path:
    d = tmp_path / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def client_factory(
    tmp_db_url: str, tmp_projects_dir: Path,
) -> Iterator[TestClient]:
    """Yields a TestClient bound to a freshly-initialised SQLite + dirs.

    The factory pattern (yielding the actual client) is more ergonomic than a
    separate ``client`` fixture for tests that need to tweak env vars before
    the lifespan runs.
    """
    prev_db = os.environ.get("LIGHTING_ENGINE_DB_URL")
    prev_proj = os.environ.get("LIGHTING_ENGINE_PROJECTS_DIR")
    os.environ["LIGHTING_ENGINE_DB_URL"] = tmp_db_url
    os.environ["LIGHTING_ENGINE_PROJECTS_DIR"] = str(tmp_projects_dir)

    # Cached engine from any prior test must be dropped so the new URL takes
    # effect. (init_db is called inside the lifespan when TestClient enters.)
    db_module.reset_engine_for_tests()

    # Shorten the stub sleep so the generation test polls quickly.
    prev_sleep = generation_routes.STUB_GENERATION_SLEEP_SECONDS
    generation_routes.STUB_GENERATION_SLEEP_SECONDS = 0.05

    # Import here so the env vars are already set when the app's modules are
    # first evaluated.
    from lighting_engine.api.app import app

    try:
        with TestClient(app) as client:
            yield client
    finally:
        generation_routes.STUB_GENERATION_SLEEP_SECONDS = prev_sleep
        if prev_db is None:
            os.environ.pop("LIGHTING_ENGINE_DB_URL", None)
        else:
            os.environ["LIGHTING_ENGINE_DB_URL"] = prev_db
        if prev_proj is None:
            os.environ.pop("LIGHTING_ENGINE_PROJECTS_DIR", None)
        else:
            os.environ["LIGHTING_ENGINE_PROJECTS_DIR"] = prev_proj
        db_module.reset_engine_for_tests()


@pytest.fixture
def client(client_factory: TestClient) -> TestClient:
    """Alias for tests that just want a ready-made client."""
    return client_factory


# ---------------------------------------------------------------------------
# Helpers to bypass the parser when tests just need a room to drive the
# clarification / generation endpoints. (Parsing a real DXF is exercised
# in ``test_projects.py`` against the bundled Delhi fixture.)
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_project(client: TestClient, tmp_db_url: str) -> dict[str, str]:
    """Insert a project + first-class room directly via SQLAlchemy so tests
    that drive clarification / generation endpoints don't pay parser cost.

    Uses a *separate* engine bound to a fresh asyncio loop (created via
    ``asyncio.run``) so it doesn't tangle with the FastAPI lifespan-owned
    engine. SQLite is just a file, so multiple engines can safely share it.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from lighting_engine.api._room_helpers import confirmed_room_from_parsed
    from lighting_engine.api.schemas import RoomTier
    from lighting_engine.api.storage import create_project, create_room
    from lighting_engine.models.geometry import Point, Room, RoomType

    project_id = str(uuid.uuid4())
    room_id = str(uuid.uuid4())

    async def _seed() -> None:
        engine = create_async_engine(tmp_db_url, future=True)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        try:
            async with factory() as session:
                await create_project(
                    session,
                    project_id=project_id,
                    name="Test project",
                    location="delhi",
                    ceiling_path=None,
                    furniture_path=None,
                    parsed_ir=None,
                )
                # Use the production helper so the fixture stays in lockstep
                # with the real construction path — same provenance dict, same
                # downstream behaviour.
                parsed_room = Room(
                    id=room_id,
                    name="Living",
                    type=RoomType.living,
                    floor_level=0,
                    polygon=[
                        Point(x=0.0, y=0.0),
                        Point(x=5.0, y=0.0),
                        Point(x=5.0, y=4.0),
                        Point(x=0.0, y=4.0),
                    ],
                    ceiling_height_m=2.7,
                )
                confirmed = confirmed_room_from_parsed(
                    parsed_room, RoomTier.first_class,
                )
                await create_room(
                    session,
                    room_id=room_id,
                    project_id=project_id,
                    name="Living",
                    confirmed=confirmed,
                    tier=RoomTier.first_class,
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_seed())
    return {"project_id": project_id, "room_id": room_id}
