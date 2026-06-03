"""Routes for asynchronous plan generation.

POST  /api/projects/{pid}/rooms/{rid}/generate   — enqueues a background task
GET   /api/jobs/{job_id}                          — polls job status
GET   /api/projects/{pid}/rooms/{rid}/plan        — fetches the latest PlanResponse

Phase 2 stub: the background task sleeps ~2s then writes a placeholder
PlanResponse with empty SVGs + zeroed LuxStats + a warning so the studio team
can wire up the polling UI before phases 3-6 land.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lighting_engine.api._generation_pipeline import run_generation_pipeline
from lighting_engine.api.db import get_session, get_session_factory
from lighting_engine.api.schemas import (
    ConfirmedRoom,
    GenerateResponse,
    JobStatus,
    JobStatusValue,
    LuxStats,
    PlanResponse,
    RoomTier,
)
from lighting_engine.api.storage import (
    create_job,
    get_job,
    get_room,
    latest_plan_for_room,
    update_job_status,
)

router = APIRouter(tags=["generation"])


# ---------------------------------------------------------------------------
# Stub background pipeline (Phase 2 — replaced in Phase 7)
# ---------------------------------------------------------------------------

# Exposed for tests so they can shorten the sleep without monkey-patching
# ``asyncio.sleep`` (which would affect anything else awaiting in the loop).
STUB_GENERATION_SLEEP_SECONDS = 2.0


def _stub_plan_response(project_id: str, room_id: str) -> PlanResponse:
    return PlanResponse(
        project_id=project_id,
        room_id=room_id,
        rcp_svg="",
        furniture_svg="",
        lux_uniformity=LuxStats(
            mean_lux=0.0,
            min_lux=0.0,
            max_lux=0.0,
            uniformity=0.0,
            target_lux=0.0,
            meets_target=False,
        ),
        fixture_schedule=[],
        design_rationale="",
        design_notes=[],
        warnings=["stub: phase 3+ not yet integrated"],
        metadata={
            "generated_at": datetime.now(UTC).isoformat(),
            "model_used": "stub",
            "prompt_cache_hit_rate": 0.0,
        },
    )


async def run_stub_generation(job_id: str, project_id: str, room_id: str) -> None:
    """Async background task: pending → running → done (or failed).

    Uses its own session because FastAPI tears down the request-scoped session
    as soon as the response is returned.
    """
    factory = get_session_factory()
    try:
        async with factory() as session:
            job = await get_job(session, job_id)
            if job is None:
                return
            await update_job_status(session, job, status=JobStatusValue.running)
            await session.commit()
    except Exception:  # noqa: BLE001 — defensive boundary at task entry
        # If we can't even flip to running, give up silently; the job stays
        # pending and the studio can retry.
        return

    try:
        await asyncio.sleep(STUB_GENERATION_SLEEP_SECONDS)
        plan = _stub_plan_response(project_id, room_id)
        async with factory() as session:
            job = await get_job(session, job_id)
            if job is None:
                return
            await update_job_status(
                session, job, status=JobStatusValue.done, result=plan,
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — record failure
        async with factory() as session:
            job = await get_job(session, job_id)
            if job is None:
                return
            await update_job_status(
                session, job, status=JobStatusValue.failed, error=str(exc),
            )
            await session.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/api/projects/{project_id}/rooms/{room_id}/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate(
    project_id: str,
    room_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> GenerateResponse:
    """Kick off a background generation job for a (project, room) pair.

    Generic-tier rooms are explicitly rejected with 501 in v1 per spec §3.1.
    """
    record = await get_room(session, project_id, room_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room {room_id} not found in project {project_id}",
        )
    try:
        tier = RoomTier(record.tier)
    except ValueError:
        tier = RoomTier.first_class
    if tier == RoomTier.generic:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Generic-tier rooms (foyer/lobby/passage/dress) are deferred "
                "to v1.1."
            ),
        )

    # Sanity-check that the required-by-generate fields are set; spec §3.3
    # mandates we return 400 with the missing list.
    confirmed = ConfirmedRoom.model_validate(record.confirmed_room)
    missing: list[str] = []
    if confirmed.ceiling_height_m is None:
        missing.append("ceiling_height_m")
    # Per spec §3.3, type_confirmed is required. type_inferred is always set
    # by the parser (RoomType, non-None), so no fallback is needed.
    if confirmed.type_confirmed is None:
        missing.append("type_confirmed")
    if confirmed.main_window_orientation is None:
        missing.append("main_window_orientation")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"missing_fields": missing},
        )

    job_id = str(uuid.uuid4())
    await create_job(
        session, job_id=job_id, project_id=project_id, room_id=room_id,
    )
    await session.commit()

    # Phase 7: real pipeline. The stub remains exposed below for tests that
    # want to assert end-to-end behaviour without the LLM cost.
    background_tasks.add_task(
        run_generation_pipeline, job_id, project_id, room_id,
    )
    return GenerateResponse(job_id=job_id)


@router.get("/api/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> JobStatus:
    job = await get_job(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    try:
        status_val = JobStatusValue(job.status)
    except ValueError:
        status_val = JobStatusValue.pending

    result_url: str | None = None
    if status_val == JobStatusValue.done:
        result_url = f"/api/projects/{job.project_id}/rooms/{job.room_id}/plan"

    return JobStatus(
        job_id=job.id,
        project_id=job.project_id,
        room_id=job.room_id,
        status=status_val,
        error=job.error,
        result_url=result_url,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/api/projects/{project_id}/rooms/{room_id}/plan",
    response_model=PlanResponse,
)
async def get_plan(
    project_id: str,
    room_id: str,
    session: AsyncSession = Depends(get_session),
) -> PlanResponse:
    record = await get_room(session, project_id, room_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room {room_id} not found in project {project_id}",
        )
    blob = await latest_plan_for_room(
        session, project_id=project_id, room_id=room_id,
    )
    if blob is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed plan for this room yet",
        )
    return PlanResponse.model_validate(blob)
