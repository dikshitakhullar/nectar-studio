"""Render a room + neighbors + furniture as a PNG for Claude vision input.

This is NOT the client-facing SVG. It's a debug-style drawing tuned for an
LLM reader: high contrast, room name big and visible, wall edges numbered,
furniture footprints labeled, openings (door / window) drawn as standard
architectural symbols. Output is 800x800 PNG bytes ready to feed into a
Claude vision content block.
"""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, FancyArrowPatch
from matplotlib.patches import Polygon as MplPolygon

from lighting_engine.models.geometry import Point, Project, Room

_DPI = 100
_SIZE_IN = 8.0  # 8 in × 100 DPI = 800 px square
_NEIGHBOR_RADIUS_M = 6.0  # show immediate neighbors only, not the whole floor


def _polygon_centroid(polygon: list[Point]) -> Point:
    n = len(polygon)
    return Point(
        x=sum(p.x for p in polygon) / n,
        y=sum(p.y for p in polygon) / n,
    )


def _outward_normal(a: Point, b: Point, centroid: Point) -> tuple[float, float]:
    """Unit normal to edge a→b, pointing away from the polygon centroid."""
    ex, ey = b.x - a.x, b.y - a.y
    length = math.hypot(ex, ey) or 1.0
    nx, ny = -ey / length, ex / length
    mid_x, mid_y = (a.x + b.x) / 2, (a.y + b.y) / 2
    if (mid_x - centroid.x) * nx + (mid_y - centroid.y) * ny < 0:
        nx, ny = -nx, -ny
    return nx, ny


def _wall_letter(i: int) -> str:
    if i < 26:
        return chr(65 + i)
    return chr(65 + (i // 26) - 1) + chr(65 + (i % 26))


def render_room_for_vision(*, project: Project, room_id: str) -> bytes:
    """Render the target room with its immediate neighbors + furniture overlay.

    Returns PNG bytes suitable for Claude vision. Designed to be legible
    to a vision model: walls labeled A/B/C/..., openings drawn as standard
    door arcs and window double-lines, furniture footprints labeled, and
    the room name set in a large readable font in the centroid.
    """
    target = next((r for r in project.rooms if r.id == room_id), None)
    fig, ax = plt.subplots(figsize=(_SIZE_IN, _SIZE_IN), dpi=_DPI)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("#fafaf7")

    if target is None or not target.polygon:
        ax.text(
            0.5, 0.5, "polygon unavailable",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=14, color="#888",
        )
    else:
        _draw(ax, project, target)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return buf.getvalue()


def _draw(ax, project: Project, target: Room) -> None:
    centroid = _polygon_centroid(target.polygon)
    xs = [p.x for p in target.polygon]
    ys = [p.y for p in target.polygon]
    bbox = (
        min(xs) - _NEIGHBOR_RADIUS_M,
        min(ys) - _NEIGHBOR_RADIUS_M,
        max(xs) + _NEIGHBOR_RADIUS_M,
        max(ys) + _NEIGHBOR_RADIUS_M,
    )
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])

    # Neighbor rooms — grayscale, ONLY on the same floor as the target
    # (multi-floor plans overlap in xy space; mixing floors makes the render
    # unreadable for Claude).
    target_floor = target.floor_level
    for r in project.rooms:
        if r.id == target.id or not r.polygon:
            continue
        if r.floor_level != target_floor:
            continue
        # Clip to the bbox — skip rooms entirely outside the rendered area
        rxs = [p.x for p in r.polygon]
        rys = [p.y for p in r.polygon]
        if max(rxs) < bbox[0] or min(rxs) > bbox[2]:
            continue
        if max(rys) < bbox[1] or min(rys) > bbox[3]:
            continue
        coords = [(p.x, p.y) for p in r.polygon]
        ax.add_patch(MplPolygon(
            coords, facecolor="#ebe9e3", edgecolor="#9a958c",
            alpha=0.7, linewidth=0.8, zorder=1,
        ))
        ax.text(
            (min(rxs) + max(rxs)) / 2, (min(rys) + max(rys)) / 2,
            r.name, ha="center", va="center",
            fontsize=8, color="#666", zorder=2,
        )

    # Target room — highlighted polygon
    coords = [(p.x, p.y) for p in target.polygon]
    ax.add_patch(MplPolygon(
        coords, facecolor="#fdf6d9", edgecolor="#1f1d1a",
        alpha=0.95, linewidth=2.0, zorder=3,
    ))

    # Wall labels at each edge midpoint, outside the room
    n = len(target.polygon)
    for i, a in enumerate(target.polygon):
        b = target.polygon[(i + 1) % n]
        mid_x, mid_y = (a.x + b.x) / 2, (a.y + b.y) / 2
        nx, ny = _outward_normal(a, b, centroid)
        label_x, label_y = mid_x + nx * 0.4, mid_y + ny * 0.4
        ax.text(
            label_x, label_y, _wall_letter(i),
            ha="center", va="center",
            fontsize=11, fontweight="bold", color="#1f1d1a",
            bbox={"facecolor": "#fafaf7", "edgecolor": "#1f1d1a",
                  "boxstyle": "round,pad=0.2", "linewidth": 0.8},
            zorder=6,
        )

    # Doors — arc swing symbol on the wall
    for d in target.doors:
        if d.wall_index is None or d.wall_index >= n:
            continue
        a = target.polygon[d.wall_index]
        b = target.polygon[(d.wall_index + 1) % n]
        ex, ey = b.x - a.x, b.y - a.y
        edge_len = math.hypot(ex, ey) or 1.0
        ux, uy = ex / edge_len, ey / edge_len
        along = d.along_wall if d.along_wall is not None else 0.5
        door_x = a.x + ex * along
        door_y = a.y + ey * along
        nx, ny = _outward_normal(a, b, centroid)
        # Inward normal — arc opens into the room
        inx, iny = -nx, -ny
        door_w = max(d.width_m or 0.9, 0.6)
        # Hinge end of door = door_x/y - ux*door_w/2; we draw a quarter arc
        hinge_x = door_x - ux * door_w / 2
        hinge_y = door_y - uy * door_w / 2
        # Hide the wall stroke under the door — small white rect
        rect = MplPolygon(
            [
                (door_x - ux * door_w / 2, door_y - uy * door_w / 2),
                (door_x + ux * door_w / 2, door_y + uy * door_w / 2),
                (door_x + ux * door_w / 2 + nx * 0.05,
                 door_y + uy * door_w / 2 + ny * 0.05),
                (door_x - ux * door_w / 2 + nx * 0.05,
                 door_y - uy * door_w / 2 + ny * 0.05),
            ],
            facecolor="#fdf6d9", edgecolor="none", zorder=4,
        )
        ax.add_patch(rect)
        # Arc: quarter circle from hinge into the room
        angle1 = math.degrees(math.atan2(uy, ux))
        angle2 = math.degrees(math.atan2(iny, inx))
        # Ensure positive sweep
        if angle2 < angle1:
            angle2 += 360
        ax.add_patch(Arc(
            (hinge_x, hinge_y), door_w * 2, door_w * 2,
            theta1=angle1, theta2=angle2,
            edgecolor="#444", linewidth=1.2, zorder=5,
        ))

    # Windows — thick double line on the wall
    for w in target.windows:
        if w.wall_index is None or w.wall_index >= n:
            continue
        a = target.polygon[w.wall_index]
        b = target.polygon[(w.wall_index + 1) % n]
        ex, ey = b.x - a.x, b.y - a.y
        edge_len = math.hypot(ex, ey) or 1.0
        ux, uy = ex / edge_len, ey / edge_len
        along = w.along_wall if w.along_wall is not None else 0.5
        win_x = a.x + ex * along
        win_y = a.y + ey * along
        win_w = max(w.width_m or 1.2, 0.6)
        nx, ny = _outward_normal(a, b, centroid)
        sx1, sy1 = win_x - ux * win_w / 2, win_y - uy * win_w / 2
        sx2, sy2 = win_x + ux * win_w / 2, win_y + uy * win_w / 2
        off = 0.06
        ax.plot(
            [sx1 - nx * off, sx2 - nx * off],
            [sy1 - ny * off, sy2 - ny * off],
            color="#2a72b8", linewidth=1.6, zorder=5,
        )
        ax.plot(
            [sx1 + nx * off, sx2 + nx * off],
            [sy1 + ny * off, sy2 + ny * off],
            color="#2a72b8", linewidth=1.6, zorder=5,
        )

    # Furniture — footprint polygons with labels
    for f in target.furniture:
        label = (f.raw_label or f.type or "furniture")[:28]
        if f.footprint:
            ax.add_patch(MplPolygon(
                [(p.x, p.y) for p in f.footprint],
                facecolor="#b48742", edgecolor="#5b3e10",
                alpha=0.55, linewidth=0.6, zorder=4,
            ))
        else:
            ax.plot(
                f.position.x, f.position.y, marker="s",
                color="#b48742", markersize=10, zorder=4,
            )
        ax.text(
            f.position.x, f.position.y, label,
            ha="center", va="center", fontsize=7,
            color="#1f1d1a", zorder=5,
        )

    # Room name big in the centroid
    ax.text(
        centroid.x, centroid.y - 0.4, target.name,
        ha="center", va="center",
        fontsize=16, fontweight="bold", color="#1f1d1a", zorder=7,
    )

    # North arrow — top-left of the target's bbox
    arrow_x = min(xs) - 0.5
    arrow_y = max(ys) + 0.5
    ax.add_patch(FancyArrowPatch(
        (arrow_x, arrow_y), (arrow_x, arrow_y + 1.5),
        arrowstyle="->,head_width=4,head_length=6",
        color="#1f1d1a", linewidth=1.5, zorder=6,
    ))
    ax.text(
        arrow_x + 0.3, arrow_y + 0.75, "N",
        ha="left", va="center", fontsize=10,
        fontweight="bold", color="#1f1d1a", zorder=6,
    )
