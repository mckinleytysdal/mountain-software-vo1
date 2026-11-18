"""Small geometry helpers: distance between GPS points and elevation gain.

Analogy: a GPS track is a string of beads. These helpers measure how long
the string is and how much it climbs.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

# Mean Earth radius in metres (IUGG value). Same constant everywhere in the
# project so distances are comparable.
EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two points given in degrees.

    The "haversine" formula treats the Earth as a sphere. Over a few hundred
    metres the error against a proper ellipsoid is well under 0.5 %.
    """
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def cumulative_distance_m(coords: Sequence[tuple[float, float]]) -> list[float]:
    """Running distance from the first point, one value per point (first is 0)."""
    out = [0.0] * len(coords)
    for i in range(1, len(coords)):
        (la1, lo1), (la2, lo2) = coords[i - 1], coords[i]
        out[i] = out[i - 1] + haversine_m(la1, lo1, la2, lo2)
    return out


def path_length_m(coords: Sequence[tuple[float, float]]) -> float:
    """Total length in metres of a list of (lat, lon) pairs."""
    if len(coords) < 2:
        return 0.0
    return cumulative_distance_m(coords)[-1]


def elevation_gain_m(elevations: Iterable[float | None], threshold_m: float = 3.0) -> float:
    """Total climb in metres, ignoring wiggles smaller than ``threshold_m``.

    GPS elevation jitters up and down by a few metres even when you stand
    still. Adding every tiny rise would invent climbing that never happened.
    So we keep a reference height and only count a climb once we are at least
    ``threshold_m`` above it; a drop of ``threshold_m`` or more resets the
    reference. Missing (None) elevations are skipped.
    """
    gain = 0.0
    ref: float | None = None
    for ele in elevations:
        if ele is None:
            continue
        if ref is None:
            ref = ele
            continue
        if ele - ref >= threshold_m:
            gain += ele - ref
            ref = ele
        elif ref - ele >= threshold_m:
            ref = ele
    return gain


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing (0 = north, 90 = east) to travel from point 1 to point 2."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360.0


def angular_difference_deg(a: float, b: float) -> float:
    """Smallest angle between two directions, 0 to 180 degrees.

    Wind direction is circular: 359 and 1 degrees are 2 degrees apart, not 358.
    """
    d = abs(a - b) % 360.0
    return 360.0 - d if d > 180.0 else d
