"""Turn a track into evenly spaced route points.

Analogy: walk the route with a 250 m rope and drop a marker at the end of
every rope length. Each marker is a "route point". Later modules attach the
weather cell and the terrain to each marker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .geo import cumulative_distance_m
from .gpx import TrackPoint

METHOD_VERSION = "resample-linear-v1"
DEFAULT_SPACING_M = 250.0


@dataclass(frozen=True)
class RoutePoint:
    seq: int
    distance_along_m: float
    lat: float
    lon: float
    ele_gpx_m: float | None
    time_utc: datetime | None


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def resample(points: list[TrackPoint], spacing_m: float = DEFAULT_SPACING_M) -> list[RoutePoint]:
    """Place a route point every ``spacing_m`` metres along the track.

    Distances are measured along the track (the rope follows every bend),
    not as the crow flies. Positions between two track points are found by
    straight-line interpolation, which is accurate at these short spacings.
    The first and last track points are always included, so the final gap is
    usually shorter than ``spacing_m``.
    """
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    if not points:
        return []
    coords = [(p.lat, p.lon) for p in points]
    cum = cumulative_distance_m(coords)
    total = cum[-1]

    targets = []
    d = 0.0
    while d < total:
        targets.append(d)
        d += spacing_m
    if not targets or total - targets[-1] > 1e-6:
        targets.append(total)

    out: list[RoutePoint] = []
    j = 0  # index of the track segment [j, j+1] we are inside
    for seq, target in enumerate(targets):
        while j < len(points) - 2 and cum[j + 1] < target:
            j += 1
        a, b = points[j], points[min(j + 1, len(points) - 1)]
        seg = cum[min(j + 1, len(points) - 1)] - cum[j]
        f = 0.0 if seg <= 0 else min(1.0, max(0.0, (target - cum[j]) / seg))
        ele = None
        if a.ele_gpx_m is not None and b.ele_gpx_m is not None:
            ele = _lerp(a.ele_gpx_m, b.ele_gpx_m, f)
        elif a.ele_gpx_m is not None or b.ele_gpx_m is not None:
            ele = a.ele_gpx_m if a.ele_gpx_m is not None else b.ele_gpx_m
        time = None
        if a.time_utc is not None and b.time_utc is not None:
            time = a.time_utc + (b.time_utc - a.time_utc) * f
        out.append(
            RoutePoint(
                seq=seq,
                distance_along_m=target,
                lat=_lerp(a.lat, b.lat, f),
                lon=_lerp(a.lon, b.lon, f),
                ele_gpx_m=ele,
                time_utc=time,
            )
        )
    return out
