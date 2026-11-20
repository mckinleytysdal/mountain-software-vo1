"""Build tiny synthetic GPX files for tests.

These are invented tracks, not copies of any real route. Real third-party
tracks are never put in tests (see CLAUDE.md data rules).
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from mountain_software.geo import EARTH_RADIUS_M

GPX11_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="synthetic-test" xmlns="http://www.topografix.com/GPX/1/1">\n'
)

START = datetime(2026, 10, 16, 10, 59, 0, tzinfo=timezone.utc)


def metres_north(lat: float, metres: float) -> float:
    """Latitude reached by walking `metres` due north from `lat`."""
    return lat + math.degrees(metres / EARTH_RADIUS_M)


def straight_line_points(length_m: float, step_m: float, lat0: float = 51.4, lon0: float = -116.3,
                         ele0: float = 2000.0, climb_per_m: float = 0.0):
    """Points due north every `step_m`, from 0 to `length_m` inclusive."""
    n = int(round(length_m / step_m))
    return [(metres_north(lat0, i * step_m), lon0, ele0 + climb_per_m * i * step_m) for i in range(n + 1)]


def gpx_from_points(points, times=None, extra_metadata: str = "", waypoints: str = "") -> str:
    """Write (lat, lon, ele) tuples as GPX 1.1 text. `times` is an optional list of datetimes."""
    rows = []
    for i, (lat, lon, ele) in enumerate(points):
        t = f"<time>{times[i].strftime('%Y-%m-%dT%H:%M:%SZ')}</time>" if times else ""
        e = f"<ele>{ele:.1f}</ele>" if ele is not None else ""
        rows.append(f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}">{e}{t}</trkpt>')
    return (
        GPX11_HEADER
        + (f"<metadata>{extra_metadata}</metadata>\n" if extra_metadata else "")
        + waypoints
        + "<trk><name>synthetic</name><trkseg>\n"
        + "\n".join(rows)
        + "\n</trkseg></trk>\n</gpx>\n"
    )


def jittery_1hz_walk(length_m: float = 3000.0, speed_m_s: float = 0.8, jitter_m: float = 2.5, seed: int = 7):
    """A slow 1 Hz walk due north with GPS-like position wobble.

    Returns (points, times, true_length_m). The wobble is random but fixed by
    `seed`, so the test result is the same every run.
    """
    rng = random.Random(seed)
    n = int(length_m / speed_m_s)
    pts, times = [], []
    for i in range(n + 1):
        along = i * speed_m_s
        north_noise = rng.gauss(0, jitter_m)
        east_noise = rng.gauss(0, jitter_m)
        lat = metres_north(51.4, along + north_noise)
        lon = -116.3 + math.degrees(east_noise / (EARTH_RADIUS_M * math.cos(math.radians(51.4))))
        pts.append((lat, lon, 2000.0 + along * 0.3 + rng.gauss(0, 1.0)))
        times.append(START + timedelta(seconds=i))
    return pts, times, n * speed_m_s
