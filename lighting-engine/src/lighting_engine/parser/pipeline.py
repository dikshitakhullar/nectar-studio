"""Top-level pipeline: file in → (Project, GapsReport) out."""

import uuid
from pathlib import Path

from ezdxf.entities.insert import Insert
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.layouts.layout import Modelspace
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.models.gaps import (
    ExtractionSummary,
    GapsReport,
    MissingItem,
    Severity,
)
from lighting_engine.models.geometry import Point, Project, Room
from lighting_engine.parser.double_height import (
    collect_non_continuous_segments,
    find_double_height_polygons,
)
from lighting_engine.parser.entities import attach_entities
from lighting_engine.parser.gaps import build_gaps_report
from lighting_engine.parser.geometry import PlanRegion, find_plan_region
from lighting_engine.parser.layers import LayerRole, classify_layers
from lighting_engine.parser.loader import load_drawing
from lighting_engine.parser.rooms import extract_rooms
from lighting_engine.parser.snap import Segment, snap_rooms_to_walls
from lighting_engine.parser.wall_cast import cast_bounding_walls_for_rooms

INCH_TO_M = 0.0254


def _wall_segments(
    msp: Modelspace, wall_layers: set[str]
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Collect boundary segments from the given layers.

    Includes both LINE entities AND the edges of LWPOLYLINE entities — many
    architects draw window frames and stone-clad walls as closed LWPolyline
    rectangles rather than 4 separate lines. Ignoring LWPolylines was missing
    ~24% of window-layer geometry on the Delhi fixture.
    """
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for e in msp.query("LINE"):
        if e.dxf.layer not in wall_layers:
            continue
        out.append((
            (float(e.dxf.start.x), float(e.dxf.start.y)),
            (float(e.dxf.end.x), float(e.dxf.end.y)),
        ))
    for e in msp.query("LWPOLYLINE"):
        if e.dxf.layer not in wall_layers:
            continue
        if not isinstance(e, LWPolyline):
            continue
        verts = [(float(v[0]), float(v[1])) for v in e.get_points()]
        for i in range(len(verts) - 1):
            out.append((verts[i], verts[i + 1]))
        if e.closed and len(verts) >= 3:
            out.append((verts[-1], verts[0]))
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


def _segments_to_local_meters(
    segments: list[Segment],
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> list[Segment]:
    """Translate wall segments from DXF units into the local-meter frame the
    Room polygons live in.
    """
    out: list[Segment] = []
    for (x1, y1), (x2, y2) in segments:
        out.append((
            ((x1 - region.min_x) * dxf_unit_to_m, (y1 - region.min_y) * dxf_unit_to_m),
            ((x2 - region.min_x) * dxf_unit_to_m, (y2 - region.min_y) * dxf_unit_to_m),
        ))
    return out


def _polygon_centroid_local_m(polygon: list[Point]) -> tuple[float, float]:
    """Cheap centroid: vertex average. Good enough for room-attachment lookup."""
    n = len(polygon)
    cx = sum(p.x for p in polygon) / n
    cy = sum(p.y for p in polygon) / n
    return cx, cy


def _attach_double_height_polygons(
    rooms: list[Room],
    dh_polygons: list[list[Point]],
) -> None:
    """Attach each double-height polygon to the room whose footprint contains
    the polygon's centroid (shapely point-in-polygon). Mutates `rooms`.

    Polygons not contained by any room are dropped — they belong to areas the
    parser didn't recognise as rooms (e.g. courtyards on a dropped duplicate
    sheet) and we can't sensibly attach them. The pipeline's `print` adds a
    diagnostic count when run as a script.
    """
    if not rooms or not dh_polygons:
        return
    room_polys = [
        ShapelyPolygon([(p.x, p.y) for p in r.polygon]) for r in rooms
    ]
    for poly_points in dh_polygons:
        cx, cy = _polygon_centroid_local_m(poly_points)
        centroid = ShapelyPoint(cx, cy)
        for room, room_poly in zip(rooms, room_polys, strict=True):
            if room_poly.contains(centroid):
                room.double_height_polygons.append(poly_points)
                break


def parse_file(
    path: Path | str,
    *,
    project_name: str,
    location: str = "delhi",
    floor_level: int = 0,
    default_ceiling_height_m: float = 2.7,
    enable_wall_cast: bool = True,
    enable_wall_snap: bool = True,
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
    # Include window/GLASS layer LINEs as boundary segments. Windows live ONLY
    # on exterior walls, so their positions are reliable exterior-wall markers
    # — they help anchor rooms that face the outside of the building (most
    # bedrooms, dining, drawing room) even when the WALL layer is incomplete
    # at the glazed opening.
    window_layers = set(layer_roles.get(LayerRole.window, []))
    window_segments = _wall_segments(msp, window_layers)
    boundary_segments = wall_segments + window_segments
    room_result = extract_rooms(
        msp, region, boundary_segments,
        default_ceiling_height_m=default_ceiling_height_m,
        dxf_unit_to_m=INCH_TO_M,
    )
    rooms = room_result.rooms

    # Wall-cast pass (large-scale translation): for each room polygon, ray-
    # cast in 4 cardinal directions to find its actual bounding walls, then
    # translate the polygon (preserving size) so its edges touch those walls.
    # Handles the case where label-based placement puts the polygon metres
    # away from any qualifying wall — outside the snap radius below. Must run
    # BEFORE the snap step so snap does its fine refinement on a polygon
    # already in the right region.
    if (enable_wall_cast or enable_wall_snap) and rooms:
        # Include non-continuous-linetype segments (HIDDEN/DASHED/etc.) as
        # additional bounding-wall candidates: where the architect draws a
        # wall dashed because it bounds a double-height void in the floor
        # above, this is the only place that wall geometry exists. Without
        # these, rooms adjacent to double-height areas (e.g. drawing room
        # bordering bar+dining whose ceiling opens to drawing room above)
        # have no wall to cast against on that side.
        non_continuous_segments = collect_non_continuous_segments(doc)
        local_meter_walls = _segments_to_local_meters(
            boundary_segments + non_continuous_segments, region, INCH_TO_M,
        )
        if enable_wall_cast:
            rooms, _translated = cast_bounding_walls_for_rooms(
                rooms, local_meter_walls,
            )
        # Wall-snap pass: re-project each room polygon's edges onto nearby
        # real wall lines so adjacent rooms that share a wall end up with
        # coincident edges (eliminating phantom gaps).
        if enable_wall_snap:
            rooms, _snapped, _rejected = snap_rooms_to_walls(
                rooms, local_meter_walls,
            )

    summary = attach_entities(
        msp, rooms, layer_roles, region=region, dxf_unit_to_m=INCH_TO_M,
    )

    # Detect double-height (open-to-below) voids from dotted/dashed linework
    # and attach each polygon to whichever room's polygon contains its
    # centroid. Polygons whose centroid sits outside every room (courtyards
    # without a labelled room, areas on a dropped duplicate sheet) are
    # silently discarded for v0 — they don't belong to any modelled room.
    dh_polygons = find_double_height_polygons(doc, region, dxf_unit_to_m=INCH_TO_M)
    _attach_double_height_polygons(rooms, dh_polygons)

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
