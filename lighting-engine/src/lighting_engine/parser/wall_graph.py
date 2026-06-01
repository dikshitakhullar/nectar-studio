"""Build a wall graph and extract closed room-face polygons via shapely.polygonize.

Real DWGs draw walls as loose LINE entities, not closed polylines. To recover
room boundaries we collect every wall-layer line as a LineString, snap nearby
endpoints to a shared vertex (real CAD files do not guarantee exact equality),
take the unary union (which breaks lines at intersections), and ask shapely to
enumerate every closed face the resulting planar graph encloses. The result
includes the room interiors plus some artefact faces (wall-thickness slivers,
building exterior) which we filter by minimum area and aspect ratio.

Coordinates throughout this module stay in DXF units (inches in our fixtures);
unit conversion happens elsewhere when building the IR.
"""

from collections.abc import Iterable

from shapely.geometry import LineString, Point as ShapelyPoint
from shapely.geometry.polygon import Polygon
from shapely.ops import polygonize, unary_union

Segment = tuple[tuple[float, float], tuple[float, float]]


def _snap_to_grid(segments: Iterable[Segment], tol: float) -> list[Segment]:
    """Quantize endpoints onto a tol-sized grid so near-coincident endpoints merge.

    A simple grid-snap is deterministic and effective: two endpoints within `tol`
    of each other round to the same grid cell. Endpoints that straddle a cell
    boundary (rare in practice — real CAD has sub-mm precision) may still miss
    each other, but that has been an acceptable trade-off in real-file tests.
    """
    out: list[Segment] = []
    for (x1, y1), (x2, y2) in segments:
        p1 = (round(x1 / tol) * tol, round(y1 / tol) * tol)
        p2 = (round(x2 / tol) * tol, round(y2 / tol) * tol)
        if p1 != p2:
            out.append((p1, p2))
    return out


def _mbr_aspect_ratio(face: Polygon) -> float:
    """Aspect ratio of the face's minimum-rotated rectangle (long side / short side).

    Used to distinguish room interiors (≤ ~4:1, even long corridors) from
    wall-thickness slivers (often 20:1 or more).
    """
    mbr = face.minimum_rotated_rectangle
    coords = list(mbr.exterior.coords)
    if len(coords) < 4:
        return float("inf")
    side1 = ShapelyPoint(coords[0]).distance(ShapelyPoint(coords[1]))
    side2 = ShapelyPoint(coords[1]).distance(ShapelyPoint(coords[2]))
    long_side, short_side = max(side1, side2), min(side1, side2)
    return long_side / short_side if short_side > 0 else float("inf")


def extract_room_faces(
    segments: Iterable[Segment],
    *,
    snap_tolerance: float = 1.0,    # DXF units (typically inches)
    min_area: float = 1440.0,       # ≈ 10 sqft in sq-inches; safely below smallest residential room
    max_aspect_ratio: float = 5.0,  # rooms are square-ish; slivers are extremely elongated
) -> list[Polygon]:
    """Return all closed room-face polygons enclosed by the given wall segments.

    `segments` are ((x1,y1),(x2,y2)) pairs in DXF units. Filters two kinds of
    noise that polygonize produces from double-line wall drawings:
    - area < min_area (decorative artefacts, tiny gaps)
    - MBR aspect ratio > max_aspect_ratio (wall-thickness slivers)
    """
    snapped = _snap_to_grid(segments, snap_tolerance) if snap_tolerance > 0 else list(segments)
    if not snapped:
        return []
    linestrings = [LineString([a, b]) for a, b in snapped]
    # unary_union breaks lines at intersections so polygonize sees every closed face
    merged = unary_union(linestrings)
    candidates = [g for g in polygonize(merged) if g.is_valid and g.area >= min_area]
    return [g for g in candidates if _mbr_aspect_ratio(g) <= max_aspect_ratio]


def innermost_face_containing(
    faces: Iterable[Polygon],
    point: tuple[float, float],
    *,
    boundary_tolerance: float = 1.0,
) -> Polygon | None:
    """Return the smallest face containing `point` — the innermost (true room).

    A label may sit inside multiple nested faces (e.g. the actual room AND the
    larger building exterior face). We pick the smallest, which is the room
    interior. If no face strictly contains the point, allow a small tolerance
    for labels that sit exactly on a wall boundary (rare but happens).
    """
    p = ShapelyPoint(point)
    face_list = list(faces)
    containing = [f for f in face_list if f.contains(p)]
    if not containing:
        containing = [f for f in face_list if f.distance(p) <= boundary_tolerance]
    if not containing:
        return None
    return min(containing, key=lambda f: f.area)
