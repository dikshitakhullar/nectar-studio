"""Detect double-height (open-to-below) regions from dotted/dashed linework.

Architectural convention: a dotted or dashed rectangle drawn INSIDE a room's
floor plan marks an area that is open to the floor below (a void / double-
height region). In DXF, every LINE and LWPOLYLINE carries a `linetype`
attribute; `CONTINUOUS` (and `BYLAYER` resolving to continuous) means a real
edge in the cutting plane, while non-continuous linetypes (`HIDDEN`, `DASHED`,
`DASHDOT`, `PHANTOM`, `CENTER`, ...) mean "not in the cutting plane": above,
below, hidden, or void.

Algorithm:
    1. Collect every LINE / LWPOLYLINE whose resolved linetype is non-continuous.
    2. Drop segments shorter than `_MIN_SEG_LEN_IN` (in source units, inches in
       the v1 fixture) — these are stipple-pattern noise from dimension marks
       and detail crosshatches.
    3. Snap endpoints to a 1-inch grid and run shapely's `polygonize` on the
       unioned linework — the union forces intersections to become explicit
       nodes and lets polygonize close loops that were otherwise broken by
       sub-inch float noise.
    4. Keep polygons with area greater than `_MIN_POLY_AREA_SQM` (skip detail
       crosshatches and stray micro-loops).
    5. Convert each surviving polygon's vertex ring to the local-meter frame
       used by the rest of the IR, and return.

If `polygonize` returns zero closed polygons after snap+union, we fall back
to the bounding box of the union: a single rectangle covering all surviving
non-continuous segments. The caller can still attach it to the nearest room
by centroid containment. (This fallback rarely fires on real plans — the
Delhi fixture produces 10 explicit polygons — but is recorded here so callers
aren't surprised by an empty list when there's clearly dotted geometry.)
"""

from collections.abc import Iterable

from ezdxf.document import Drawing
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.layouts.layout import Modelspace
from shapely.geometry import LineString
from shapely.geometry.polygon import Polygon as ShapelyPolygon
from shapely.ops import polygonize, unary_union

from lighting_engine.models.geometry import Point
from lighting_engine.parser.geometry import PlanRegion

# ---------------------------------------------------------------------------
# Tuneables
# ---------------------------------------------------------------------------

# Linetype names that should be treated as "solid / continuous" — anything else
# is considered a non-continuous (dotted/dashed/hidden) line. Comparison is
# case-insensitive.
_CONTINUOUS_LINETYPES: frozenset[str] = frozenset({"CONTINUOUS", "BYBLOCK", ""})

# Minimum segment length to keep, in DXF source units (inches in the v1
# fixture; the loader rejects non-inch files). 12 inches ≈ 0.3 m — below this
# threshold we're looking at dimension marks, hatch stipple, or block detail.
_MIN_SEG_LEN_IN: float = 12.0

# Endpoint-snap grid in DXF source units. 1 inch is small enough not to
# distort the geometry but large enough to merge endpoints that are within
# float-noise distance of each other (the Delhi fixture has endpoints offset
# by ~0.5–1.0 inch from each other on intended-coincident vertices).
_SNAP_GRID_IN: float = 1.0

# Minimum polygon area in square metres. A real double-height region is room-
# sized (typically ≥ 4 sqm). 1 sqm is a generous floor that still rejects
# small detail loops while keeping any plausible void.
_MIN_POLY_AREA_SQM: float = 1.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_double_height_polygons(
    dxf_doc: Drawing,
    plan_region: PlanRegion,
    *,
    dxf_unit_to_m: float = 0.0254,
) -> list[list[Point]]:
    """Detect double-height (open-to-below) polygons in a parsed DXF document.

    Returns a list of polygons (each polygon is a list of `Point` in the
    plan-local meter frame, same convention as `Room.polygon`). Empty list if
    no dotted/dashed loops large enough to be void regions are found.
    """
    msp = dxf_doc.modelspace()
    layer_lt = _layer_linetype_map(dxf_doc)
    segments = _collect_non_continuous_segments(msp, layer_lt)
    segments = _filter_by_length(segments, _MIN_SEG_LEN_IN)
    segments = _filter_to_region(segments, plan_region)
    if not segments:
        return []

    snapped = _snap_endpoints(segments, _SNAP_GRID_IN)
    polys = _polygonize_snapped(snapped)
    if not polys:
        # Fallback: bounding box of the unioned linework. Documented above.
        fallback = _bounding_box_fallback(snapped)
        if fallback is None:
            return []
        polys = [fallback]

    min_area_in_sq = _MIN_POLY_AREA_SQM / (dxf_unit_to_m * dxf_unit_to_m)
    out: list[list[Point]] = []
    for poly in polys:
        if poly.area < min_area_in_sq:
            continue
        out.append(_polygon_to_local_meters(poly, plan_region, dxf_unit_to_m))
    return out


def collect_non_continuous_segments(
    dxf_doc: Drawing,
    *,
    min_seg_len_in: float = _MIN_SEG_LEN_IN,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Return all LINE / LWPOLYLINE segments whose effective linetype is non-
    continuous (HIDDEN, DASHED, DASHDOT, PHANTOM, CENTER, etc.), in DXF source
    units.

    These segments mark architectural features outside the cutting plane —
    void boundaries above/below, double-height edges, hidden walls. They are
    also valid bounding-wall candidates for wall-cast / wall-snap: when a
    floor's structural wall is drawn dashed because it bounds a double-height
    void in the room above, this is the only place that wall geometry shows
    up. Pass through the same length filter the double-height detector uses
    so micro-noise stippling is dropped.
    """
    msp = dxf_doc.modelspace()
    layer_lt = _layer_linetype_map(dxf_doc)
    segments = _collect_non_continuous_segments(msp, layer_lt)
    return _filter_by_length(segments, min_seg_len_in)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _layer_linetype_map(doc: Drawing) -> dict[str, str]:
    """Map layer name -> the layer's default linetype (used to resolve BYLAYER)."""
    return {layer.dxf.name: layer.dxf.linetype for layer in doc.layers}


def _resolve_linetype(entity_lt: str, layer_name: str, layer_lt: dict[str, str]) -> str:
    """Return the effective linetype: resolve `BYLAYER` to the layer's setting."""
    if entity_lt.upper() == "BYLAYER":
        return layer_lt.get(layer_name, "CONTINUOUS")
    return entity_lt


def _is_non_continuous(linetype: str) -> bool:
    return linetype.upper() not in _CONTINUOUS_LINETYPES


def _collect_non_continuous_segments(
    msp: Modelspace,
    layer_lt: dict[str, str],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Collect every LINE / LWPOLYLINE edge whose effective linetype is non-continuous."""
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []

    for e in msp.query("LINE"):
        lt = _resolve_linetype(str(e.dxf.linetype), str(e.dxf.layer), layer_lt)
        if not _is_non_continuous(lt):
            continue
        x1 = float(e.dxf.start.x)
        y1 = float(e.dxf.start.y)
        x2 = float(e.dxf.end.x)
        y2 = float(e.dxf.end.y)
        out.append(((x1, y1), (x2, y2)))

    for e in msp.query("LWPOLYLINE"):
        if not isinstance(e, LWPolyline):
            continue
        lt = _resolve_linetype(str(e.dxf.linetype), str(e.dxf.layer), layer_lt)
        if not _is_non_continuous(lt):
            continue
        verts = [(float(v[0]), float(v[1])) for v in e.get_points()]
        for i in range(len(verts) - 1):
            out.append((verts[i], verts[i + 1]))
        if e.closed and len(verts) >= 3:
            out.append((verts[-1], verts[0]))

    return out


def _filter_by_length(
    segments: Iterable[tuple[tuple[float, float], tuple[float, float]]],
    min_len: float,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    min_len_sq = min_len * min_len
    for (x1, y1), (x2, y2) in segments:
        dx = x2 - x1
        dy = y2 - y1
        if dx * dx + dy * dy >= min_len_sq:
            out.append(((x1, y1), (x2, y2)))
    return out


def _filter_to_region(
    segments: Iterable[tuple[tuple[float, float], tuple[float, float]]],
    region: PlanRegion,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Keep segments whose midpoint lies inside the plan region bbox."""
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for (x1, y1), (x2, y2) in segments:
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        if region.contains((mx, my)):
            out.append(((x1, y1), (x2, y2)))
    return out


def _snap_endpoints(
    segments: Iterable[tuple[tuple[float, float], tuple[float, float]]],
    grid: float,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Snap each endpoint to a `grid`-spaced lattice; drop zero-length segments."""
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for (x1, y1), (x2, y2) in segments:
        a = (round(x1 / grid) * grid, round(y1 / grid) * grid)
        b = (round(x2 / grid) * grid, round(y2 / grid) * grid)
        if a == b:
            continue
        out.append((a, b))
    return out


def _polygonize_snapped(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[ShapelyPolygon]:
    """Union all line segments (so intersections become nodes) and polygonize."""
    if not segments:
        return []
    lines = [LineString(s) for s in segments]
    merged = unary_union(lines)
    polys: list[ShapelyPolygon] = []
    for p in polygonize(merged):
        # polygonize is typed as returning iterable of geometries; in practice
        # every yielded shape is a Polygon, but skip empties defensively.
        if not p.is_empty:
            polys.append(p)
    return polys


def _bounding_box_fallback(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> ShapelyPolygon | None:
    """Last-resort polygon: axis-aligned bbox of all surviving segments.

    Used when shapely can't close any loops from the dotted linework — better
    to attach a rough bounding rectangle to a room than to lose the signal
    entirely.
    """
    if not segments:
        return None
    xs = [v for (a, b) in segments for v in (a[0], b[0])]
    ys = [v for (a, b) in segments for v in (a[1], b[1])]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmin == xmax or ymin == ymax:
        return None
    return ShapelyPolygon([
        (xmin, ymin),
        (xmax, ymin),
        (xmax, ymax),
        (xmin, ymax),
    ])


def _polygon_to_local_meters(
    poly: ShapelyPolygon,
    region: PlanRegion,
    dxf_unit_to_m: float,
) -> list[Point]:
    """Convert a shapely polygon (DXF units) into a list[Point] in the local-meter frame."""
    out: list[Point] = []
    # Skip the closing duplicate vertex shapely appends to exterior rings.
    coords = list(poly.exterior.coords)
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    for x_in, y_in in coords:
        out.append(Point(
            x=(float(x_in) - region.min_x) * dxf_unit_to_m,
            y=(float(y_in) - region.min_y) * dxf_unit_to_m,
        ))
    return out


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def collect_linetype_summary(dxf_doc: Drawing) -> dict[str, int]:
    """Return a count of every effective linetype seen on LINE / LWPOLYLINE entities.

    Useful for debug prints — confirms which linetype names actually appear in
    a given DXF (and therefore which non-continuous styles are present).
    """
    msp = dxf_doc.modelspace()
    layer_lt = _layer_linetype_map(dxf_doc)
    counts: dict[str, int] = {}
    for e in msp.query("LINE LWPOLYLINE"):
        lt = _resolve_linetype(str(e.dxf.linetype), str(e.dxf.layer), layer_lt)
        counts[lt] = counts.get(lt, 0) + 1
    return counts
