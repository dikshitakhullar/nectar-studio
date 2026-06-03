"""Routes for room clarifications: basics, walls, furniture, brief.

All POST handlers merge their payload into the stored ``ConfirmedRoom`` blob
following the merge rules in spec §3.3 (user > parser; touched fields gain a
``provenance: "user"`` marker).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lighting_engine.api.db import get_session
from lighting_engine.api.models import RoomRecord
from lighting_engine.api.schemas import (
    BriefRequest,
    ClarificationRequest,
    ConfirmedRoom,
    FurnitureRequest,
    RoomTier,
    WallConfirmation,
    WallsResponse,
)
from lighting_engine.api.storage import (
    get_room,
    update_room_confirmed,
)

router = APIRouter(prefix="/api/projects", tags=["rooms"])


async def _load_confirmed(
    session: AsyncSession, project_id: str, room_id: str,
) -> tuple[ConfirmedRoom, RoomTier, str, RoomRecord]:
    """Load and parse the stored ConfirmedRoom blob for a (project, room) pair.

    Returns ``(confirmed, tier, status, room_record)``. The record is handed
    back so the caller can persist updates without re-querying.
    """
    record = await get_room(session, project_id, room_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room {room_id} not found in project {project_id}",
        )
    confirmed = ConfirmedRoom.model_validate(record.confirmed_room)
    try:
        tier = RoomTier(record.tier)
    except ValueError:
        tier = RoomTier.first_class
    return confirmed, tier, record.status, record


@router.get("/{project_id}/rooms/{room_id}", response_model=ConfirmedRoom)
async def get_room_endpoint(
    project_id: str,
    room_id: str,
    session: AsyncSession = Depends(get_session),
) -> ConfirmedRoom:
    confirmed, _tier, _status, _record = await _load_confirmed(
        session, project_id, room_id,
    )
    return confirmed


@router.post("/{project_id}/rooms/{room_id}", response_model=ConfirmedRoom)
async def post_room_basics(
    project_id: str,
    room_id: str,
    payload: ClarificationRequest,
    session: AsyncSession = Depends(get_session),
) -> ConfirmedRoom:
    """Merge /studio/room-basics clarifications into the ConfirmedRoom."""
    confirmed, _tier, _status, record = await _load_confirmed(
        session, project_id, room_id,
    )

    touched: list[str] = []
    if payload.type_confirmed is not None:
        confirmed.type_confirmed = payload.type_confirmed
        touched.append("type_confirmed")
    if payload.length_m is not None:
        confirmed.length_m = payload.length_m
        touched.append("length_m")
    if payload.width_m is not None:
        confirmed.width_m = payload.width_m
        touched.append("width_m")
    if payload.ceiling_height_m is not None:
        confirmed.ceiling_height_m = payload.ceiling_height_m
        touched.append("ceiling_height_m")
    if payload.ceiling_type is not None:
        confirmed.ceiling_type = payload.ceiling_type
        touched.append("ceiling_type")
    if payload.main_window_orientation is not None:
        confirmed.main_window_orientation = payload.main_window_orientation
        touched.append("main_window_orientation")
    if payload.occupants is not None:
        confirmed.occupants = list(payload.occupants)
        touched.append("occupants")
    if payload.floor_finish is not None:
        confirmed.floor_finish = payload.floor_finish
        touched.append("floor_finish")
    if payload.wall_finish is not None:
        confirmed.wall_finish = payload.wall_finish
        touched.append("wall_finish")

    for field in touched:
        confirmed.provenance[field] = "user"

    await update_room_confirmed(
        session, record, confirmed, status="basics_confirmed" if touched else None,
    )
    await session.commit()
    return confirmed


@router.get("/{project_id}/rooms/{room_id}/walls", response_model=WallsResponse)
async def get_room_walls(
    project_id: str,
    room_id: str,
    session: AsyncSession = Depends(get_session),
) -> WallsResponse:
    confirmed, _tier, _status, _record = await _load_confirmed(
        session, project_id, room_id,
    )
    # If the user hasn't touched walls yet, derive a default list from the
    # parsed polygon (one entry per edge).
    if not confirmed.walls:
        walls = [
            WallConfirmation(index=i, confirm=False)
            for i in range(len(confirmed.polygon_inferred))
        ]
    else:
        walls = list(confirmed.walls)
    return WallsResponse(project_id=project_id, room_id=room_id, walls=walls)


@router.post(
    "/{project_id}/rooms/{room_id}/walls/{wall_index}",
    response_model=ConfirmedRoom,
)
async def post_room_wall(
    project_id: str,
    room_id: str,
    wall_index: int,
    payload: WallConfirmation,
    session: AsyncSession = Depends(get_session),
) -> ConfirmedRoom:
    """Update a single wall confirmation."""
    if wall_index < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="wall_index must be non-negative",
        )
    if payload.index != wall_index:
        # Be lenient: rewrite the body's index to match the URL.
        payload = payload.model_copy(update={"index": wall_index})

    confirmed, _tier, _status, record = await _load_confirmed(
        session, project_id, room_id,
    )
    # Ensure walls list is at least wall_index+1 long.
    while len(confirmed.walls) <= wall_index:
        confirmed.walls.append(WallConfirmation(index=len(confirmed.walls)))
    confirmed.walls[wall_index] = payload
    confirmed.provenance[f"walls[{wall_index}]"] = "user"
    await update_room_confirmed(
        session, record, confirmed, status="walls_confirmed",
    )
    await session.commit()
    return confirmed


@router.post(
    "/{project_id}/rooms/{room_id}/furniture",
    response_model=ConfirmedRoom,
)
async def post_room_furniture(
    project_id: str,
    room_id: str,
    payload: FurnitureRequest,
    session: AsyncSession = Depends(get_session),
) -> ConfirmedRoom:
    confirmed, _tier, _status, record = await _load_confirmed(
        session, project_id, room_id,
    )
    if payload.furniture_notes:
        confirmed.furniture_notes = payload.furniture_notes
        confirmed.provenance["furniture_notes"] = "user"
    if payload.mood is not None:
        confirmed.intent_mood = payload.mood
        confirmed.provenance["intent_mood"] = "user"
    if payload.activities:
        confirmed.activities = list(payload.activities)
        confirmed.provenance["activities"] = "user"
    await update_room_confirmed(
        session, record, confirmed, status="furniture_confirmed",
    )
    await session.commit()
    return confirmed


@router.post(
    "/{project_id}/rooms/{room_id}/brief",
    response_model=ConfirmedRoom,
)
async def post_room_brief(
    project_id: str,
    room_id: str,
    payload: BriefRequest,
    session: AsyncSession = Depends(get_session),
) -> ConfirmedRoom:
    confirmed, _tier, _status, record = await _load_confirmed(
        session, project_id, room_id,
    )
    if payload.intent_mood is not None:
        confirmed.intent_mood = payload.intent_mood
        confirmed.provenance["intent_mood"] = "user"
    if payload.activities:
        confirmed.activities = list(payload.activities)
        confirmed.provenance["activities"] = "user"
    if payload.time_of_use:
        confirmed.time_of_use = list(payload.time_of_use)
        confirmed.provenance["time_of_use"] = "user"
    await update_room_confirmed(
        session, record, confirmed, status="brief_confirmed",
    )
    await session.commit()
    return confirmed
