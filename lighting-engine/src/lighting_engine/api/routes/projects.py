"""Routes for ``/api/projects`` and ``/api/projects/{pid}/rooms``."""

import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from lighting_engine.api._room_helpers import (
    classify_tier,
    confirmed_room_from_parsed,
    room_summary_from_record,
)
from lighting_engine.api.db import get_session
from lighting_engine.api.schemas import (
    ConfirmedRoom,
    ProjectCreateResponse,
    RoomListResponse,
    RoomSummary,
    RoomTier,
)
from lighting_engine.api.storage import (
    create_project,
    create_room,
    get_project,
    list_rooms,
)
from lighting_engine.parser.pipeline import parse_file

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _projects_storage_root() -> Path:
    """Where uploaded DWG/DXF files are persisted.

    Override-able via ``LIGHTING_ENGINE_PROJECTS_DIR`` for tests / staging
    environments. Defaults to ``<lighting-engine>/data/projects``.
    """
    env = os.environ.get("LIGHTING_ENGINE_PROJECTS_DIR")
    if env:
        return Path(env)
    # src/lighting_engine/api/routes/projects.py → root is parents[4]
    root = Path(__file__).resolve().parents[4]
    return root / "data" / "projects"


def _save_upload(upload: UploadFile, dest: Path) -> None:
    """Stream an UploadFile to disk."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        shutil.copyfileobj(upload.file, fh)


@router.post(
    "",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project from DWG/DXF uploads",
)
async def create_project_endpoint(
    ceiling: UploadFile = File(..., description="Ceiling DWG or DXF file"),
    furniture: UploadFile | None = File(
        default=None, description="Furniture DWG or DXF file (optional in Phase 2)",
    ),
    project_name: str = Form(default="Untitled project"),
    location: str = Form(default="delhi"),
    session: AsyncSession = Depends(get_session),
) -> ProjectCreateResponse:
    """Upload a ceiling (+ optional furniture) drawing and parse it.

    Phase 2: only the ceiling file is parsed; the furniture upload is stored
    on disk for later phases.
    """
    project_id = str(uuid.uuid4())
    project_dir = _projects_storage_root() / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    ceiling_suffix = Path(ceiling.filename or "ceiling.dxf").suffix or ".dxf"
    ceiling_path = project_dir / f"ceiling{ceiling_suffix}"
    _save_upload(ceiling, ceiling_path)

    furniture_path: Path | None = None
    if furniture is not None:
        furniture_suffix = (
            Path(furniture.filename or "furniture.dxf").suffix or ".dxf"
        )
        furniture_path = project_dir / f"furniture{furniture_suffix}"
        _save_upload(furniture, furniture_path)

    try:
        project, _gaps = parse_file(
            ceiling_path, project_name=project_name, location=location,
        )
    except Exception as exc:  # parser surfaces ezdxf errors as plain Exception
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse ceiling file: {exc}",
        ) from exc

    # Override the parser-assigned project id with the one we generated so the
    # FK relationships line up.
    parsed_ir = project.model_dump(mode="json")

    await create_project(
        session,
        project_id=project_id,
        name=project_name,
        location=location,
        ceiling_path=str(ceiling_path),
        furniture_path=str(furniture_path) if furniture_path else None,
        parsed_ir=parsed_ir,
    )

    summaries: list[RoomSummary] = []
    for room in project.rooms:
        tier = classify_tier(room.type)
        if tier is None:
            # Hidden tier — not surfaced in the picker.
            continue
        confirmed = confirmed_room_from_parsed(room, tier)
        await create_room(
            session,
            room_id=room.id,
            project_id=project_id,
            name=room.name,
            confirmed=confirmed,
            tier=tier,
        )
        summaries.append(
            room_summary_from_record(
                room_id=room.id,
                name=room.name,
                tier=tier,
                status="new",
                confirmed=confirmed,
            )
        )

    await session.commit()

    return ProjectCreateResponse(project_id=project_id, rooms=summaries)


@router.get(
    "/{project_id}/rooms",
    response_model=RoomListResponse,
    summary="List rooms for a project",
)
async def list_project_rooms(
    project_id: str,
    session: AsyncSession = Depends(get_session),
) -> RoomListResponse:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    records = await list_rooms(session, project_id)

    summaries: list[RoomSummary] = []
    for rec in records:
        confirmed = ConfirmedRoom.model_validate(rec.confirmed_room)
        try:
            tier = RoomTier(rec.tier)
        except ValueError:
            tier = RoomTier.first_class
        summaries.append(
            room_summary_from_record(
                room_id=rec.id,
                name=rec.name,
                tier=tier,
                status=rec.status,
                confirmed=confirmed,
            )
        )
    return RoomListResponse(rooms=summaries)
