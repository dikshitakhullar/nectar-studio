"""Real generation pipeline: ConfirmedRoom → PlanResponse.

Glues together the brief layer (Step 5), multi-layer placement (Step 4),
lux uniformity, and the SVG renderers per spec §2.2. The routes module
calls `run_generation_pipeline` as a FastAPI BackgroundTask.

`generate_room_brief` is imported here at module level so tests can patch
`lighting_engine.api._generation_pipeline.generate_room_brief` with a fake
to avoid live LLM calls.
"""

from collections import OrderedDict
from datetime import UTC, datetime

from lighting_engine.api.db import get_session_factory
from lighting_engine.api.schemas import (
    ConfirmedRoom,
    FixtureRow,
    JobStatusValue,
    PlanResponse,
)
from lighting_engine.api.schemas import LuxStats as ApiLuxStats
from lighting_engine.api.storage import get_job, get_room, update_job_status
from lighting_engine.brief.generator import generate_room_brief
from lighting_engine.brief.models import (
    BriefInput,
    ConfirmedRoomInput,
    DesignerBrief,
    FixtureCatalogOption,
    StandardsSnapshot,
)
from lighting_engine.digest import compute_digest
from lighting_engine.lighting.fixtures import (
    DEFAULT_COOL_DOWNLIGHT,
    DEFAULT_WARM_DOWNLIGHT,
)
from lighting_engine.lighting.multi_layer import compute_all_fixtures
from lighting_engine.lighting.standards import get_lux_standard
from lighting_engine.lux.uniformity import compute_uniformity
from lighting_engine.models.geometry import Fixture, Project, Room
from lighting_engine.render.furniture import render_furniture_svg
from lighting_engine.render.rcp import render_rcp_svg


def _confirmed_to_room(confirmed: ConfirmedRoom) -> Room:
    """Hydrate a ConfirmedRoom blob into a `Room` domain object.

    The user's `type_confirmed` overrides the parser's `type_inferred` when
    set. Ceiling height falls back to 2.7m (residential default) only if
    every other safeguard upstream has failed — `POST /generate` is supposed
    to reject with 400 when ceiling_height_m is None per spec §3.3, so this
    fallback is defensive only.
    """
    room_type = confirmed.type_confirmed or confirmed.type_inferred
    ceiling_h = confirmed.ceiling_height_m or 2.7
    return Room(
        id=confirmed.id,
        name=confirmed.name,
        type=room_type,
        floor_level=0,
        polygon=list(confirmed.polygon_inferred),
        ceiling_height_m=ceiling_h,
        doors=list(confirmed.doors_parsed),
        windows=list(confirmed.windows_parsed),
        furniture=list(confirmed.furniture_parsed),
        ceiling_features=list(confirmed.ceiling_features_parsed),
    )


def _fixture_catalog() -> list[FixtureCatalogOption]:
    """Project `lighting/fixtures.py` defaults into the brief input shape.

    For v1 we expose two archetypes (warm + cool downlights). The LLM picks
    layer/CCT/fixture_type per zone; the placement code uses these specs as
    defaults when filling in actual fixtures.
    """
    return [
        FixtureCatalogOption(
            sku=spec.sku, name=spec.name, wattage_w=spec.wattage_w,
            lumens=spec.lumens, cct_k=spec.cct_k, cri=spec.cri,
            beam_angle_deg=spec.beam_angle_deg,
        )
        for spec in (DEFAULT_WARM_DOWNLIGHT, DEFAULT_COOL_DOWNLIGHT)
    ]


def _build_brief_input(confirmed: ConfirmedRoom, digest: object) -> BriefInput:
    """Project ConfirmedRoom + room-type standards into the brief input."""
    room_type = confirmed.type_confirmed or confirmed.type_inferred
    standard = get_lux_standard(room_type)

    designer = DesignerBrief(
        intent_mood=confirmed.intent_mood or "cozy",
        activities=list(confirmed.activities),
        time_of_use=list(confirmed.time_of_use),
        occupants=list(confirmed.occupants),
        floor_finish=confirmed.floor_finish,
        wall_finish=confirmed.wall_finish,
        notes=confirmed.furniture_notes,
    )

    # ConfirmedRoomInput's `main_window_orientation` is `N|S|E|W|none` —
    # ConfirmedRoom uses `N|S|E|W` (none-valued when unset). Map None → 'none'.
    orientation_in = confirmed.main_window_orientation
    orientation = orientation_in.value if orientation_in else "none"

    # `ConfirmedRoomInput` is intentionally minimal: only the fields the LLM
    # needs that AREN'T already in the digest. The room's type and dimensions
    # are sourced from the digest + standards table.
    confirmed_input = ConfirmedRoomInput(
        ceiling_type=(confirmed.ceiling_type.value
                      if confirmed.ceiling_type else "flat"),
        main_window_orientation=orientation,
        designer_brief=designer,
    )

    return BriefInput(
        digest=digest,           # type: ignore[arg-type] — pydantic accepts the RoomDigest instance
        confirmed_room=confirmed_input,
        standards=StandardsSnapshot(
            target_lux=standard.target_lux,
            cct_k=standard.cct_k,
            cri_min=standard.cri_min,
        ),
        fixture_catalog=_fixture_catalog(),
    )


def _build_fixture_schedule(fixtures: list[Fixture]) -> list[FixtureRow]:
    """Group `Fixture`s by spec into wire-format `FixtureRow`s for the report.

    Stable key: (type, wattage_w, cct_k, cri, beam_angle_deg). Uses an
    OrderedDict so the schedule preserves the order fixtures were placed
    in — designers expect ambient → task → accent → decorative.
    """
    groups: OrderedDict[
        tuple[str, float, int, int, float],
        tuple[Fixture, int],
    ] = OrderedDict()
    for f in fixtures:
        key = (
            f.type,
            f.wattage_w or 0.0,
            f.cct_k or 0,
            f.cri or 0,
            f.beam_angle_deg or 0.0,
        )
        prev = groups.get(key)
        if prev is None:
            groups[key] = (f, 1)
        else:
            groups[key] = (prev[0], prev[1] + 1)

    rows: list[FixtureRow] = []
    for (ftype, watts, cct, cri, beam), (f, count) in groups.items():
        sku = f"{ftype}-{int(watts)}w-{cct}k".lower().replace(" ", "-")
        name = (
            f"{int(watts)}W {ftype} {cct}K CRI{cri or '?'}"
            f"{' (60°)' if beam == 60.0 else f' ({int(beam)}°)' if beam else ''}"
        )
        rows.append(FixtureRow(
            sku=sku, name=name, wattage_w=watts, lumens=f.lumens or 0.0,
            cct_k=cct, cri=cri, beam_angle_deg=beam, count=count,
        ))
    return rows


def _to_api_lux_stats(stats: object) -> ApiLuxStats:
    """Drop `sample_count` from `lux.uniformity.LuxStats` for the wire format."""
    # `stats` is a `lux.uniformity.LuxStats`; uses model_dump so we tolerate
    # any future fields the lux module adds without breaking the API contract.
    payload = stats.model_dump()  # type: ignore[attr-defined]
    return ApiLuxStats(
        mean_lux=payload["mean_lux"],
        min_lux=payload["min_lux"],
        max_lux=payload["max_lux"],
        uniformity=payload["uniformity"],
        target_lux=payload["target_lux"],
        meets_target=payload["meets_target"],
    )


def _build_plan_response(
    *, project_id: str, room_id: str,
    confirmed: ConfirmedRoom,
) -> PlanResponse:
    """The actual orchestration: ConfirmedRoom → PlanResponse."""
    room = _confirmed_to_room(confirmed)
    project = Project(id=project_id, name=confirmed.name, rooms=[room])
    digest = compute_digest(project).rooms[0]

    brief_input = _build_brief_input(confirmed, digest)
    brief = generate_room_brief(brief_input)

    fixtures = compute_all_fixtures(room, digest, brief)
    raw_stats = compute_uniformity(
        room, fixtures, target_lux=brief.target_lux_ambient,
    )

    rcp = render_rcp_svg(room, fixtures)
    lamps = list(brief.floor_lamp_suggestions) + list(brief.table_lamp_suggestions)
    furniture = render_furniture_svg(room, lamps)

    return PlanResponse(
        project_id=project_id,
        room_id=room_id,
        rcp_svg=rcp,
        furniture_svg=furniture,
        lux_uniformity=_to_api_lux_stats(raw_stats),
        fixture_schedule=_build_fixture_schedule(fixtures),
        design_rationale=brief.design_rationale,
        design_notes=list(brief.design_notes),
        warnings=list(brief.warnings),
        metadata={
            "generated_at": datetime.now(UTC).isoformat(),
            "model_used": "claude-opus-4-7",
            "fixture_count": len(fixtures),
        },
    )


async def run_generation_pipeline(
    job_id: str, project_id: str, room_id: str,
) -> None:
    """Background task entry point. Owns its own session.

    Status transitions: pending → running → done | failed. On any exception
    the job moves to failed with the exception's str() as the error message
    — the studio surfaces this in `/studio/generating`.
    """
    factory = get_session_factory()
    # Phase 1: flip pending → running, snapshot the ConfirmedRoom.
    try:
        async with factory() as session:
            job = await get_job(session, job_id)
            if job is None:
                return
            await update_job_status(session, job, status=JobStatusValue.running)
            await session.commit()
            record = await get_room(session, project_id, room_id)
            if record is None:
                raise RuntimeError(
                    f"Room {room_id} disappeared between enqueue and run",
                )
            confirmed = ConfirmedRoom.model_validate(record.confirmed_room)
    except Exception:   # noqa: BLE001
        # Couldn't even start — give up; the job stays pending and the
        # studio can retry. Defensive boundary; failures here are infra
        # issues (DB connection lost mid-task), not data issues.
        return

    # Phase 2: run the pipeline outside any DB session so the LLM call
    # doesn't hold a connection for 5-15s.
    try:
        plan = _build_plan_response(
            project_id=project_id, room_id=room_id, confirmed=confirmed,
        )
    except Exception as exc:   # noqa: BLE001 — record failure cleanly
        async with factory() as session:
            job = await get_job(session, job_id)
            if job is not None:
                await update_job_status(
                    session, job, status=JobStatusValue.failed,
                    error=f"{type(exc).__name__}: {exc}",
                )
                await session.commit()
        return

    # Phase 3: persist the result.
    async with factory() as session:
        job = await get_job(session, job_id)
        if job is None:
            return
        await update_job_status(
            session, job, status=JobStatusValue.done, result=plan,
        )
        await session.commit()
