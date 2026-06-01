"""Find the bounding region of the actual plan, rejecting stray entities.

Real Indian residential DWGs often have title-block content or stray geometry
far from the main drawing. The furniture fixture had ~20% strays scattered out
to X=347,000 inches, polluting a naive bbox to 214,000 inches wide. We cluster
entity centroids by 1D gaps in X (and Y) and keep the dominant cluster.
"""

from dataclasses import dataclass

# Stray-rejection gap threshold in DXF units (typically inches): if two adjacent
# X-positions are >5000 inches (≈ 417 ft) apart, they belong to different clusters.
# A residential plan rarely exceeds ~5000 inches in either dimension.
_CLUSTER_GAP = 5000.0


@dataclass(frozen=True)
class PlanRegion:
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    outliers_rejected: int

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def contains(self, point: tuple[float, float]) -> bool:
        x, y = point
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y


def _dominant_cluster(values: list[float], gap: float) -> list[float]:
    """Return the largest contiguous cluster in `values` (1D), split by `gap`."""
    if not values:
        return []
    sorted_v = sorted(values)
    clusters: list[list[float]] = [[sorted_v[0]]]
    for v in sorted_v[1:]:
        if v - clusters[-1][-1] > gap:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return max(clusters, key=len)


def find_plan_region(
    points: list[tuple[float, float]],
    cluster_gap: float = _CLUSTER_GAP,
) -> PlanRegion:
    """Detect the real plan bbox from a list of entity centroid (x,y) positions.

    The dominant 1D cluster in X and in Y is kept; everything else is rejected.
    """
    if not points:
        raise ValueError("find_plan_region: no points provided")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_keep = set(_dominant_cluster(xs, cluster_gap))
    y_keep = set(_dominant_cluster(ys, cluster_gap))

    kept = [(x, y) for x, y in points if x in x_keep and y in y_keep]
    rejected = len(points) - len(kept)

    if not kept:
        # All points were rejected — fall back to using everything
        kept = points
        rejected = 0

    return PlanRegion(
        min_x=min(p[0] for p in kept),
        min_y=min(p[1] for p in kept),
        max_x=max(p[0] for p in kept),
        max_y=max(p[1] for p in kept),
        outliers_rejected=rejected,
    )
