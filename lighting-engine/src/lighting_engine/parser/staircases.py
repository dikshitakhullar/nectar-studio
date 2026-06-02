"""Staircase detection from UP / DN text labels.

Architects mark stair treads with `UP` or `DN` arrows rather than labelling the
staircase as a room with dimensions. This module finds those markers, clusters
nearby ones into a single staircase, and returns anchor points that the room
extractor can turn into Rooms tagged `RoomType.staircase`.

Per the design doc §5: label-based detection in v0; geometric tread-detection
(stair-arc / run-and-rise analysis) is deferred to v1.
"""

import math
import re
from dataclasses import dataclass, field

from ezdxf.entities.line import Line
from ezdxf.entities.mtext import MText
from ezdxf.entities.text import Text
from ezdxf.layouts.layout import Modelspace

from lighting_engine.parser.mtext import strip_mtext_codes

# Two UP/DN labels within this distance (DXF units, typically inches) are
# treated as part of the same staircase. 200 inches ≈ 17ft — enough to span a
# typical residential stair flight, tight enough that distinct staircases on
# the same floor stay separate.
DEFAULT_CLUSTER_DISTANCE_IN = 200.0

# Match standalone UP, DN, DOWN markers — bounded by start/end of text or
# whitespace so we don't catch "UPPER FLOOR" or "DOWNSTAIRS" or "BACKUP".
_STAIR_RE = re.compile(r"^\s*(UP|DN|DOWN)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class StaircaseAnchor:
    """A detected staircase, located at the centroid of its UP/DN labels.

    When tread geometry is found nearby on the STEPS layer, ``tread_bbox_in``
    is set to ``(xmin, ymin, xmax, ymax)`` (in DXF units) and ``(x, y)`` is
    the centroid of that tread cluster.  Otherwise ``tread_bbox_in`` is ``None``
    and ``(x, y)`` is the centroid of the UP/DN label positions.
    """

    x: float
    y: float
    has_up: bool
    has_dn: bool
    # Set when STEPS-layer tread geometry was found nearby.
    # When set, (x, y) is the tread cluster centroid; otherwise the label centroid.
    tread_bbox_in: tuple[float, float, float, float] | None = field(default=None)


def _collect_stair_label_positions(
    msp: Modelspace,
) -> list[tuple[str, float, float]]:
    """Walk text entities; return (marker, x, y) tuples for each UP/DN label."""
    out: list[tuple[str, float, float]] = []
    for e in msp.query("MTEXT TEXT"):
        if isinstance(e, MText):
            raw = e.text
        elif isinstance(e, Text):
            raw = e.dxf.text
        else:
            continue
        try:
            ip = e.dxf.insert
        except AttributeError:
            continue
        cleaned = strip_mtext_codes(raw)
        m = _STAIR_RE.match(cleaned)
        if not m:
            continue
        marker = m.group(1).upper()
        if marker == "DOWN":
            marker = "DN"
        out.append((marker, float(ip.x), float(ip.y)))
    return out


def cluster_staircase_labels(
    positions: list[tuple[str, float, float]],
    *,
    max_distance_in: float = DEFAULT_CLUSTER_DISTANCE_IN,
) -> list[list[tuple[str, float, float]]]:
    """Single-link cluster UP/DN positions by Euclidean proximity.

    Two positions belong to the same cluster if any pair of points in the cluster
    are within `max_distance_in` of each other. Returns a list of clusters where
    each cluster is the list of original (marker, x, y) tuples.
    """
    if not positions:
        return []
    n = len(positions)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    max_sq = max_distance_in * max_distance_in
    for i in range(n):
        for j in range(i + 1, n):
            dx = positions[i][1] - positions[j][1]
            dy = positions[i][2] - positions[j][2]
            if dx * dx + dy * dy <= max_sq:
                union(i, j)

    groups: dict[int, list[tuple[str, float, float]]] = {}
    for i, pos in enumerate(positions):
        groups.setdefault(find(i), []).append(pos)
    return list(groups.values())


def _find_nearby_tread_cluster(
    msp: Modelspace,
    anchor_x: float,
    anchor_y: float,
    *,
    search_radius: float = 300.0,
    min_lines: int = 5,
) -> tuple[tuple[float, float, float, float], tuple[float, float]] | None:
    """Look on the STEPS layer for ≥min_lines LINE entities within
    search_radius of (anchor_x, anchor_y). If found, return
    (bbox=(xmin, ymin, xmax, ymax), centroid=(cx, cy)). Else None.

    Layer name match is case-insensitive — ``STEPS``, ``Steps``, ``steps`` all
    count.  A LINE is considered "within range" when at least one of its two
    endpoints is within ``search_radius`` of the anchor.
    """
    radius_sq = search_radius * search_radius
    nearby: list[Line] = []
    for entity in msp.query("LINE"):
        if not isinstance(entity, Line):
            continue
        if entity.dxf.layer.upper() != "STEPS":
            continue
        start = entity.dxf.start
        end = entity.dxf.end
        # Accept the line if either endpoint is within the search radius.
        for px, py in ((start.x, start.y), (end.x, end.y)):
            dx = px - anchor_x
            dy = py - anchor_y
            if dx * dx + dy * dy <= radius_sq:
                nearby.append(entity)
                break

    if len(nearby) < min_lines:
        return None

    # Additionally require that the cluster contains ≥ min_lines lines that
    # are mutually parallel (same angle mod 180°) — this filters incidental
    # stray STEPS entities that happen to be in the search radius.
    angle_counts: dict[float, int] = {}
    for entity in nearby:
        start = entity.dxf.start
        end = entity.dxf.end
        dx = end.x - start.x
        dy = end.y - start.y
        if dx == 0.0 and dy == 0.0:
            continue  # degenerate zero-length line
        # Round angle to nearest degree (mod 180) to group parallel lines.
        angle = round(math.degrees(math.atan2(dy, dx)) % 180.0)
        angle_counts[angle] = angle_counts.get(angle, 0) + 1

    if not angle_counts or max(angle_counts.values()) < min_lines:
        return None

    # Compute bbox over all nearby STEPS endpoints.
    xs: list[float] = []
    ys: list[float] = []
    for entity in nearby:
        start = entity.dxf.start
        end = entity.dxf.end
        xs.extend((start.x, end.x))
        ys.extend((start.y, end.y))

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    return (xmin, ymin, xmax, ymax), (cx, cy)


def detect_staircase_anchors(
    msp: Modelspace,
    *,
    max_distance_in: float = DEFAULT_CLUSTER_DISTANCE_IN,
) -> list[StaircaseAnchor]:
    """Walk the modelspace, find UP/DN labels, cluster them, return one anchor
    per cluster.

    For each cluster, the function additionally searches for STEPS-layer tread
    geometry within 300 DXF units of the label centroid.  If ≥5 parallel LINE
    entities are found, the anchor's ``(x, y)`` is set to the tread-cluster
    centroid and ``tread_bbox_in`` is populated.  Otherwise ``(x, y)`` is the
    label centroid and ``tread_bbox_in`` is ``None``.
    """
    positions = _collect_stair_label_positions(msp)
    clusters = cluster_staircase_labels(positions, max_distance_in=max_distance_in)
    anchors: list[StaircaseAnchor] = []
    for cluster in clusters:
        label_cx = sum(p[1] for p in cluster) / len(cluster)
        label_cy = sum(p[2] for p in cluster) / len(cluster)
        markers = {p[0] for p in cluster}

        tread = _find_nearby_tread_cluster(msp, label_cx, label_cy)
        if tread is not None:
            bbox, (cx, cy) = tread
            anchors.append(StaircaseAnchor(
                x=cx, y=cy,
                has_up="UP" in markers,
                has_dn="DN" in markers,
                tread_bbox_in=bbox,
            ))
        else:
            anchors.append(StaircaseAnchor(
                x=label_cx, y=label_cy,
                has_up="UP" in markers,
                has_dn="DN" in markers,
                tread_bbox_in=None,
            ))
    return anchors
