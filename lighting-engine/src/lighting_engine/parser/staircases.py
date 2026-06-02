"""Staircase detection from UP / DN text labels.

Architects mark stair treads with `UP` or `DN` arrows rather than labelling the
staircase as a room with dimensions. This module finds those markers, clusters
nearby ones into a single staircase, and returns anchor points that the room
extractor can turn into Rooms tagged `RoomType.staircase`.

Per the design doc §5: label-based detection in v0; geometric tread-detection
(stair-arc / run-and-rise analysis) is deferred to v1.
"""

import re
from dataclasses import dataclass

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
    """A detected staircase, located at the centroid of its UP/DN labels."""
    x: float
    y: float
    has_up: bool
    has_dn: bool


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


def detect_staircase_anchors(
    msp: Modelspace,
    *,
    max_distance_in: float = DEFAULT_CLUSTER_DISTANCE_IN,
) -> list[StaircaseAnchor]:
    """Walk the modelspace, find UP/DN labels, cluster them, return one anchor
    per cluster (the centroid of its UP/DN labels).
    """
    positions = _collect_stair_label_positions(msp)
    clusters = cluster_staircase_labels(positions, max_distance_in=max_distance_in)
    anchors: list[StaircaseAnchor] = []
    for cluster in clusters:
        cx = sum(p[1] for p in cluster) / len(cluster)
        cy = sum(p[2] for p in cluster) / len(cluster)
        markers = {p[0] for p in cluster}
        anchors.append(StaircaseAnchor(
            x=cx, y=cy,
            has_up="UP" in markers,
            has_dn="DN" in markers,
        ))
    return anchors
