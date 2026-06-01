"""Top-level pipeline: file in → (Project, GapsReport) out."""

import uuid
from pathlib import Path

from ezdxf.entities.insert import Insert
from ezdxf.layouts.layout import Modelspace

from lighting_engine.models.gaps import (
    ExtractionSummary,
    GapsReport,
    MissingItem,
    Severity,
)
from lighting_engine.models.geometry import Project
from lighting_engine.parser.entities import attach_entities
from lighting_engine.parser.gaps import build_gaps_report
from lighting_engine.parser.geometry import find_plan_region
from lighting_engine.parser.layers import LayerRole, classify_layers
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.rooms import extract_rooms

INCH_TO_M = 0.0254


def _wall_segments(
    msp: Modelspace, wall_layers: set[str]
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for e in msp.query("LINE"):
        if e.dxf.layer not in wall_layers:
            continue
        out.append((
            (float(e.dxf.start.x), float(e.dxf.start.y)),
            (float(e.dxf.end.x), float(e.dxf.end.y)),
        ))
    return out


def _wall_centroids(msp: Modelspace, wall_layers: set[str]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for e in msp.query("LINE"):
        if e.dxf.layer not in wall_layers:
            continue
        out.append((
            (float(e.dxf.start.x) + float(e.dxf.end.x)) / 2,
            (float(e.dxf.start.y) + float(e.dxf.end.y)) / 2,
        ))
    return out


def _has_north_arrow(msp: Modelspace, north_layers: set[str]) -> bool:
    return any(
        isinstance(e, Insert) and e.dxf.layer in north_layers
        for e in msp.query("INSERT")
    )


def parse_file(
    path: Path | str,
    *,
    project_name: str,
    location: str = "delhi",
    floor_level: int = 0,
    default_ceiling_height_m: float = 2.7,
) -> tuple[Project, GapsReport]:
    """Parse a single DWG/DXF into a Project + GapsReport.

    DXF units are assumed to be inches (real Delhi DWGs use INSUNITS=1). The
    loader will reject non-inch files in strict mode.
    """
    load = load_drawing(path)
    doc = load.document
    msp = doc.modelspace()

    layer_names = [layer.dxf.name for layer in doc.layers]
    layer_roles = classify_layers(layer_names)
    wall_layers = set(layer_roles.get(LayerRole.wall, []))

    wall_centroids = _wall_centroids(msp, wall_layers)
    if not wall_centroids:
        report = GapsReport(extraction=ExtractionSummary())
        report.missing.append(MissingItem(
            category="walls",
            description="No wall geometry found on any wall-named layer",
            severity=Severity.high,
        ))
        empty = Project(
            id=str(uuid.uuid4()),
            name=project_name,
            location=location,
            floor_level=floor_level,
        )
        return empty, report

    region = find_plan_region(wall_centroids)
    wall_segments = _wall_segments(msp, wall_layers)
    room_result = extract_rooms(
        msp, region, wall_segments,
        default_ceiling_height_m=default_ceiling_height_m,
        dxf_unit_to_m=INCH_TO_M,
    )
    rooms = room_result.rooms
    summary = attach_entities(
        msp, rooms, layer_roles, region=region, dxf_unit_to_m=INCH_TO_M,
    )

    north_found = _has_north_arrow(msp, set(layer_roles.get(LayerRole.north_arrow, [])))
    report = build_gaps_report(
        rooms, summary,
        north_arrow_found=north_found,
        height_labels_found=0,   # designer fills via brief
    )
    if room_result.rect_fallback_room_ids:
        report.missing.append(MissingItem(
            category="room_polygon_fallback",
            description=(
                f"{len(room_result.rect_fallback_room_ids)} room(s) used label-rect "
                f"polygon (insufficient walls found): "
                f"{', '.join(room_result.rect_fallback_room_ids[:5])}"
                + ("..." if len(room_result.rect_fallback_room_ids) > 5 else "")
            ),
            severity=Severity.medium,
        ))

    project = Project(
        id=str(uuid.uuid4()),
        name=project_name,
        location=location,
        floor_level=floor_level,
        rooms=rooms,
    )
    return project, report
