"""Module 4: relative exposure to potential wind loading.

Two methods are compared:

* B0, the baseline: a slope counts as "leeward" when it faces away from the
  wind, within a fixed angle. It ignores terrain shape, wind strength and snow.
* M1, the terrain index: for every hour, how much snow the wind could move
  (wind above a threshold, with fresh snow available), times how sheltered
  or exposed the point is from that hour's wind direction (Sx from the DEM).
  Sheltered hours add "loading", exposed hours add "scour".

The output is a RELATIVE index: points are ranked against the other points
of the same route and window, 0 = least exposure to potential loading, 1 =
most. It is not a hazard rating and says nothing about whether a slope will
avalanche.

Analogy: B0 asks "is this slope on the back side of the wind?". M1 asks
"how much snow was blowing around, and does this spot sit in a pocket where
blowing snow would drop, or on a bump where it gets stripped?".
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from ..geo import angular_difference_deg

B0_VERSION = "b0-aspect-v1"
M1_VERSION = "m1-sx-transport-v3"


@dataclass(frozen=True)
class ExposureParams:
    # B0: leeward if aspect is within this many degrees of the downwind direction.
    b0_half_window_deg: float = 45.0
    # M1: which model wind drives transport. "700hPa" = free-atmosphere wind
    # near ridge-top height (default); "10m" = wind 10 m above the smoothed
    # model surface, which in these valleys rarely exceeds 20 km/h.
    wind_level: str = "700hPa"
    # M1: hourly wind (km/h) below which no snow is assumed to move.
    # Avalanche Canada: light wind (1-25 km/h) moves little snow; moderate
    # (25-40 km/h) is most conducive to wind slabs. Li & Pomeroy (1997) give
    # 7.7 m/s (28 km/h) mean for dry snow at 10 m over flat ground.
    transport_threshold_kmh: float = 25.0
    # M1: total blowing-snow transport grows with about the 4th power of wind
    # speed (Pomeroy, Gray & Landine 1991, via Pomeroy & Brun 2001).
    transport_exponent: float = 4.0
    # M1: fresh snow (cm) over the previous 72 h that counts as "full supply";
    # older snow still supplies a little (``old_snow_supply``).
    fresh_snow_full_cm: float = 20.0
    fresh_snow_hours: int = 72
    old_snow_supply: float = 0.2
    # M1: Sx search distance (must exist in route_point_sx). Winstral et al.
    # (2002) found 100 m best on a fine DEM; on a 30 m DEM that is only 3
    # cells, so 300 m (the MeteoIO/CHM default) is used, 100 m as a check.
    sx_dmax_m: float = 300.0
    # Window: hours before the as-of time that are summed.
    window_hours: int = 72
    # A run is published 1-3 h after its nominal time (Open-Meteo docs for
    # regional models). A run only counts as known once this lag has passed.
    publication_lag_hours: float = 3.0


# ------------------------------------------------------------------ weather


@dataclass
class HourlyWeather:
    valid_time: datetime
    wind_speed_kmh: float | None
    wind_from_deg: float | None
    snowfall_cm: float | None
    product: str
    issue_time: datetime | None


def _parse(t: str | None) -> datetime | None:
    return None if t is None else datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def best_available_weather(
    conn: sqlite3.Connection,
    cell_id: int,
    start: datetime,
    end: datetime,
    as_of: datetime,
    allow_stitched: bool = True,
    publication_lag_hours: float = 3.0,
    wind_level: str = "700hPa",
) -> list[HourlyWeather]:
    """Hourly weather for one cell, using only forecasts published by ``as_of``.

    For each hour pick the most recent model run that was already published
    at ``as_of`` (issue time + publication lag <= as_of), i.e. the shortest
    lead time available then. This is what someone could have known at
    ``as_of``: no look-ahead. If no such run covers an
    hour and ``allow_stitched`` is True, fall back to the stitched archive
    value, which is flagged because its issue time is unknown.
    """
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    if wind_level == "700hPa":
        spd, dirn = "wind_speed_700hpa_kmh", "wind_direction_700hpa_deg"
    elif wind_level == "10m":
        spd, dirn = "wind_speed_10m_kmh", "wind_direction_10m_deg"
    else:
        raise ValueError(f"unknown wind_level {wind_level!r}")
    rows = conn.execute(
        f"""SELECT valid_time_utc, issue_time_utc, {spd}, {dirn}, snowfall_cm
           FROM forecast_snapshots
           WHERE cell_id = ? AND product = 'single_run' AND valid_time_utc BETWEEN ? AND ? AND issue_time_utc <= ?
           ORDER BY valid_time_utc, issue_time_utc DESC""",
        (cell_id, start.strftime(fmt), end.strftime(fmt), (as_of - timedelta(hours=publication_lag_hours)).strftime(fmt)),
    ).fetchall()
    best: dict[str, HourlyWeather] = {}
    for r in rows:
        if r[0] in best:
            continue  # already have a newer run for this hour
        best[r[0]] = HourlyWeather(_parse(r[0]), r[2], r[3], r[4], "single_run", _parse(r[1]))
    if allow_stitched:
        for r in conn.execute(
            f"""SELECT valid_time_utc, {spd}, {dirn}, snowfall_cm FROM forecast_snapshots
               WHERE cell_id = ? AND product = 'historical_stitched' AND valid_time_utc BETWEEN ? AND ?""",
            (cell_id, start.strftime(fmt), end.strftime(fmt)),
        ):
            best.setdefault(r[0], HourlyWeather(_parse(r[0]), r[1], r[2], r[3], "historical_stitched", None))
    return [best[k] for k in sorted(best)]


# ------------------------------------------------------------------ B0


def b0_leeward(aspect_deg: float | None, wind_from_deg: float | None, half_window_deg: float) -> bool | None:
    """True if the slope faces downwind (within ``half_window_deg``).

    Wind FROM 270 (west) blows TOWARDS 90 (east); an east-facing slope is
    leeward. Flat ground (no aspect) or calm (no direction) gives None.
    """
    if aspect_deg is None or wind_from_deg is None:
        return None
    downwind = (wind_from_deg + 180.0) % 360.0
    return angular_difference_deg(aspect_deg, downwind) <= half_window_deg


# ------------------------------------------------------------------ M1


def transport_potential(wind_kmh: float | None, threshold_kmh: float, exponent: float) -> float:
    """Relative amount of snow the wind could move in one hour (0 if calm).

    (U / Ut)^n - 1 above the threshold Ut: zero at the threshold, then
    growing with the n-th power of wind speed (n = 4 for total transport).
    """
    if wind_kmh is None or wind_kmh <= threshold_kmh:
        return 0.0
    return (wind_kmh / threshold_kmh) ** exponent - 1.0


def snow_supply(recent_snowfall_cm: float, full_cm: float, old_snow: float) -> float:
    """0..1: how much loose snow is available to blow around."""
    return old_snow + (1.0 - old_snow) * min(1.0, max(0.0, recent_snowfall_cm) / full_cm)


def sx_for_direction(sx_by_dir: dict[float, float], wind_from_deg: float) -> float | None:
    """Sx for any direction, interpolated between the stored 10° directions."""
    if not sx_by_dir:
        return None
    dirs = sorted(sx_by_dir)
    step = dirs[1] - dirs[0] if len(dirs) > 1 else 360.0
    lo = (math.floor(wind_from_deg / step) * step) % 360.0
    hi = (lo + step) % 360.0
    if lo not in sx_by_dir or hi not in sx_by_dir:
        nearest = min(dirs, key=lambda d: angular_difference_deg(d, wind_from_deg))
        return sx_by_dir[nearest]
    f = ((wind_from_deg - lo) % 360.0) / step
    a, b = sx_by_dir[lo], sx_by_dir[hi]
    if a is None or b is None:
        return a if b is None else b
    return a + (b - a) * f


@dataclass
class PointResult:
    seq: int
    b0_leeward_fraction: float | None
    m1_loading: float
    m1_scour: float
    m1_net: float
    hours_used: int
    hours_stitched: int


def score_point(
    weather: list[HourlyWeather],
    aspect_deg: float | None,
    sx_by_dir: dict[float, float],
    p: ExposureParams,
) -> PointResult:
    """B0 and M1 for one route point over one window of hourly weather."""
    loading = scour = 0.0
    lee_weight = total_weight = 0.0
    snowfall = [(w.valid_time, w.snowfall_cm or 0.0) for w in weather]
    used = stitched = 0
    for w in weather:
        if w.wind_speed_kmh is None or w.wind_from_deg is None:
            continue
        used += 1
        stitched += w.product == "historical_stitched"
        recent = sum(s for t, s in snowfall if w.valid_time - timedelta(hours=p.fresh_snow_hours) < t <= w.valid_time)
        q = transport_potential(w.wind_speed_kmh, p.transport_threshold_kmh, p.transport_exponent)
        q *= snow_supply(recent, p.fresh_snow_full_cm, p.old_snow_supply)
        lee = b0_leeward(aspect_deg, w.wind_from_deg, p.b0_half_window_deg)
        if lee is not None:
            total_weight += 1.0
            lee_weight += 1.0 if lee else 0.0
        sxv = sx_for_direction(sx_by_dir, w.wind_from_deg)
        if sxv is None or q == 0.0:
            continue
        shelter = math.sin(math.radians(sxv))  # -1..1, 0 = level upwind
        if shelter > 0:
            loading += q * shelter
        else:
            scour += q * -shelter
    return PointResult(
        seq=-1,
        b0_leeward_fraction=(lee_weight / total_weight) if total_weight else None,
        m1_loading=loading,
        m1_scour=scour,
        m1_net=loading - scour,
        hours_used=used,
        hours_stitched=stitched,
    )


def relative_rank(values: list[float | None]) -> list[float | None]:
    """Turn raw scores into 0..1 ranks within the set (ties share a rank).

    If every value is the same there is nothing to rank, so all ranks are
    None ("not informative") rather than a misleading 0.5.
    """
    finite = [v for v in values if v is not None and math.isfinite(v)]
    if not finite or (len(finite) > 1 and max(finite) == min(finite)):
        return [None] * len(values)
    arr = np.array(finite)
    out = []
    for v in values:
        if v is None or not math.isfinite(v):
            out.append(None)
        elif len(arr) == 1:
            out.append(0.5)
        else:
            below = float(np.sum(arr < v))
            equal = float(np.sum(arr == v))
            out.append((below + (equal - 1) / 2) / (len(arr) - 1))
    return out


@dataclass
class RouteExposure:
    route_id: str
    as_of: datetime
    window_start: datetime
    window_end: datetime
    points: list[PointResult]
    newest_issue_time: datetime | None
    stitched_fraction: float
    params: ExposureParams

    @property
    def data_age_hours(self) -> float | None:
        if self.newest_issue_time is None:
            return None
        return (self.as_of - self.newest_issue_time).total_seconds() / 3600


def route_exposure(
    conn: sqlite3.Connection,
    route_id: str,
    as_of: datetime,
    params: ExposureParams | None = None,
    allow_stitched: bool = True,
) -> RouteExposure:
    """Score every route point for the ``window_hours`` ending at ``as_of``."""
    p = params or ExposureParams()
    start = as_of - timedelta(hours=p.window_hours)
    pts = conn.execute(
        """SELECT tf.seq, tf.aspect_true_deg, rpc.cell_id FROM terrain_features tf
           JOIN route_point_cells rpc ON rpc.route_id = tf.route_id AND rpc.seq = tf.seq
           WHERE tf.route_id = ? ORDER BY tf.seq""",
        (route_id,),
    ).fetchall()
    if not pts:
        raise ValueError(f"route {route_id} needs route points with terrain features and weather cells")
    sx_rows = conn.execute(
        "SELECT seq, wind_from_true_deg, sx_deg FROM route_point_sx WHERE route_id = ? AND dmax_m = ?",
        (route_id, p.sx_dmax_m),
    ).fetchall()
    sx: dict[int, dict[float, float]] = {}
    for seq, d, v in sx_rows:
        sx.setdefault(seq, {})[d] = v

    weather_cache: dict[int, list[HourlyWeather]] = {}
    results = []
    newest: datetime | None = None
    n_hours = n_stitched = 0
    for seq, aspect, cell_id in pts:
        if cell_id not in weather_cache:
            weather_cache[cell_id] = best_available_weather(
                conn, cell_id, start, as_of, as_of, allow_stitched, p.publication_lag_hours, p.wind_level
            )
        wx = weather_cache[cell_id]
        r = score_point(wx, aspect, sx.get(seq, {}), p)
        r.seq = seq
        results.append(r)
    for wx in weather_cache.values():
        for w in wx:
            n_hours += 1
            n_stitched += w.product == "historical_stitched"
            if w.issue_time and (newest is None or w.issue_time > newest):
                newest = w.issue_time
    return RouteExposure(
        route_id=route_id,
        as_of=as_of,
        window_start=start,
        window_end=as_of,
        points=results,
        newest_issue_time=newest,
        stitched_fraction=(n_stitched / n_hours) if n_hours else 1.0,
        params=p,
    )


def store_exposure(conn: sqlite3.Connection, ex: RouteExposure) -> int:
    """Write B0 and M1 rows to ``exposure_scores`` (replacing the same run)."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    m1_rel = relative_rank([r.m1_net for r in ex.points])
    b0_rel = relative_rank([r.b0_leeward_fraction for r in ex.points])
    inputs = json.dumps(
        {
            "params": asdict(ex.params),
            "newest_issue_time_utc": ex.newest_issue_time.strftime(fmt) if ex.newest_issue_time else None,
            "stitched_fraction": ex.stitched_fraction,
        },
        sort_keys=True,
    )
    rows = []
    for r, m1r, b0r in zip(ex.points, m1_rel, b0_rel):
        detail = {"loading": r.m1_loading, "scour": r.m1_scour, "hours_used": r.hours_used, "hours_stitched": r.hours_stitched}
        rows.append((ex.route_id, r.seq, "B0", B0_VERSION, r.b0_leeward_fraction, b0r, json.dumps({"hours_used": r.hours_used})))
        rows.append((ex.route_id, r.seq, "M1", M1_VERSION, r.m1_net, m1r, json.dumps(detail, sort_keys=True)))
    with conn:
        conn.execute(
            "DELETE FROM exposure_scores WHERE route_id = ? AND as_of_utc = ?", (ex.route_id, ex.as_of.strftime(fmt))
        )
        conn.executemany(
            f"""INSERT INTO exposure_scores (route_id, seq, method, method_version, as_of_utc, window_start_utc,
                window_end_utc, data_age_hours, inputs_json, raw_score, relative_index, detail_json, created_at_utc)
               VALUES (?, ?, ?, ?, '{ex.as_of.strftime(fmt)}', '{ex.window_start.strftime(fmt)}',
                '{ex.window_end.strftime(fmt)}', ?, ?, ?, ?, ?, ?)""",
            [
                (rid, seq, m, v, ex.data_age_hours, inputs, raw, rel, det, datetime.now(UTC).strftime(fmt))
                for (rid, seq, m, v, raw, rel, det) in rows
            ],
        )
    return len(rows)
