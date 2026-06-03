"""Thin async data-access helpers around the ORM models.

These functions wrap ``AsyncSession`` so the route handlers stay focused on
HTTP semantics, not SQLAlchemy syntax.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lighting_engine.api.models import Job, Project, RoomRecord
from lighting_engine.api.schemas import (
    ConfirmedRoom,
    JobStatusValue,
    PlanResponse,
    RoomTier,
)

# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

async def create_project(
    session: AsyncSession,
    *,
    project_id: str,
    name: str,
    location: str,
    ceiling_path: str | None,
    furniture_path: str | None,
    parsed_ir: dict[str, Any] | None,
) -> Project:
    project = Project(
        id=project_id,
        name=name,
        location=location,
        ceiling_path=ceiling_path,
        furniture_path=furniture_path,
        parsed_ir=parsed_ir,
    )
    session.add(project)
    await session.flush()
    return project


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    return await session.get(Project, project_id)


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

async def create_room(
    session: AsyncSession,
    *,
    room_id: str,
    project_id: str,
    name: str,
    confirmed: ConfirmedRoom,
    tier: RoomTier,
) -> RoomRecord:
    room = RoomRecord(
        id=room_id,
        project_id=project_id,
        name=name,
        confirmed_room=confirmed.model_dump(mode="json"),
        tier=tier.value,
        status="new",
    )
    session.add(room)
    await session.flush()
    return room


async def list_rooms(session: AsyncSession, project_id: str) -> list[RoomRecord]:
    stmt = select(RoomRecord).where(RoomRecord.project_id == project_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_room(
    session: AsyncSession, project_id: str, room_id: str,
) -> RoomRecord | None:
    room = await session.get(RoomRecord, room_id)
    if room is None or room.project_id != project_id:
        return None
    return room


async def update_room_confirmed(
    session: AsyncSession,
    room: RoomRecord,
    confirmed: ConfirmedRoom,
    *,
    status: str | None = None,
) -> RoomRecord:
    room.confirmed_room = confirmed.model_dump(mode="json")
    if status is not None:
        room.status = status
    room.updated_at = datetime.now(UTC)
    await session.flush()
    return room


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

async def create_job(
    session: AsyncSession,
    *,
    job_id: str,
    project_id: str,
    room_id: str,
) -> Job:
    job = Job(
        id=job_id,
        project_id=project_id,
        room_id=room_id,
        status=JobStatusValue.pending.value,
    )
    session.add(job)
    await session.flush()
    return job


async def get_job(session: AsyncSession, job_id: str) -> Job | None:
    return await session.get(Job, job_id)


async def update_job_status(
    session: AsyncSession,
    job: Job,
    *,
    status: JobStatusValue,
    error: str | None = None,
    result: PlanResponse | None = None,
) -> Job:
    job.status = status.value
    if error is not None:
        job.error = error
    if result is not None:
        job.result = result.model_dump(mode="json")
    job.updated_at = datetime.now(UTC)
    await session.flush()
    return job


async def latest_plan_for_room(
    session: AsyncSession,
    *,
    project_id: str,
    room_id: str,
) -> dict[str, Any] | None:
    """Return the most-recent completed job's result blob for this room, or
    ``None`` if no job has finished yet."""
    stmt = (
        select(Job)
        .where(
            Job.project_id == project_id,
            Job.room_id == room_id,
            Job.status == JobStatusValue.done.value,
        )
        .order_by(Job.updated_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        return None
    return job.result
