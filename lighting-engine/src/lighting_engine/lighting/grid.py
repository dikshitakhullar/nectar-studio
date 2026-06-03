"""Ambient downlight grid placement.

Given a room polygon (axis-aligned in v0), a fixture count, and a maximum
spacing, lay the fixtures out on a regular grid with perimeter offset so the
cones overlap and walls aren't darkened.

Standard residential practice:
- Perimeter offset = half-spacing (downlights at 0.6–0.9m from walls)
- Roughly equal row/column spacing matching the room's aspect ratio
"""

import math

from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.polygon import Polygon as ShapelyPolygon

from lighting_engine.models.geometry import Point


def _bbox(polygon: list[Point]) -> tuple[float, float, float, float]:
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _grid_dimensions(count: int, width: float, height: float) -> tuple[int, int]:
    """Pick (cols, rows) so cols × rows = count and the shape matches aspect.

    Solves a small constrained optimisation: choose integer cols, rows such that
    cols * rows ≥ count and (width/cols) ≈ (height/rows).
    """
    if count <= 1:
        return 1, 1
    aspect = max(width, 1e-6) / max(height, 1e-6)
    # Ideal cols if cells were truly equal: cols = sqrt(count * aspect)
    cols = max(1, round(math.sqrt(count * aspect)))
    rows = max(1, math.ceil(count / cols))
    # Tighten in case we overshot
    while (cols - 1) * rows >= count and cols > 1:
        cols -= 1
    while cols * (rows - 1) >= count and rows > 1:
        rows -= 1
    return cols, rows


def compute_ambient_grid(
    polygon: list[Point],
    fixture_count: int,
    *,
    max_spacing_m: float | None = None,
) -> list[Point]:
    """Lay `fixture_count` fixtures on a grid inside `polygon`.

    `max_spacing_m`: if provided, the grid may add ROWS/COLS to keep spacing
    below this cap (S/MH ratio constraint). The returned count may exceed the
    input `fixture_count` when honoring this cap on a long room.

    Returns positions in the polygon's local-meter frame, in row-major order.
    """
    if fixture_count <= 0 or not polygon:
        return []

    xmin, ymin, xmax, ymax = _bbox(polygon)
    width = xmax - xmin
    height = ymax - ymin
    if width <= 0 or height <= 0:
        return []

    cols, rows = _grid_dimensions(fixture_count, width, height)

    # Honor the S/MH-derived max spacing by inflating the grid if needed.
    if max_spacing_m is not None and max_spacing_m > 0:
        while width / cols > max_spacing_m:
            cols += 1
        while height / rows > max_spacing_m:
            rows += 1

    # Equal interior spacing with half-spacing perimeter offset.
    col_step = width / cols
    row_step = height / rows
    poly_shapely = ShapelyPolygon([(p.x, p.y) for p in polygon])

    positions: list[Point] = []
    for r in range(rows):
        for c in range(cols):
            x = xmin + col_step * (c + 0.5)
            y = ymin + row_step * (r + 0.5)
            if poly_shapely.contains(ShapelyPoint(x, y)):
                positions.append(Point(x=x, y=y))
    return positions
