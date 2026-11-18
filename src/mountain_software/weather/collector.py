"""Find weather cells, collect forecasts, and backfill from the archive.

Vocabulary used below (each defined once):

* cell: one square of the weather model's grid (about 2.5 km for HRDPS). All
  route points inside one cell share the same weather numbers.
* issue time: when a forecast was made (the model run time).
* valid time: the hour the forecast is about.
* lead hours: valid time minus issue time. A 30-hour lead means "forecast
  made 30 hours ahead".
* look-ahead bias: accidentally using information that was not available
  yet at the time. Keeping issue time and valid time apart prevents it.
* idempotent: running something twice leaves the same result as running it
  once. Every write here is an "upsert" (insert, or update if already there).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..geo import haversine_m
from . import openmeteo as om

CELL_METHOD_VERSION = "cell-nearest-v1"
SNAPSHOT_METHOD_VERSION = "openmeteo-hrdps-raw-v1"
DEFAULT_RAW_DIR = Path("data/raw")
BATCH_SIZE = 50
DEFAULT_BACKFILL_RUN_HOURS = (0, 12)
ISSUE_NOTE_SINGLE = "true issue time: the model run (initialisation) time requested from the Single Runs API"
ISSUE_NOTE_STITCHED = (
    "unknown: Historical Forecast API stitches the first hours of successive runs and does not report "
    "which run each hour came from; not a true forecast"
)
ISSUE_NOTE_DISCOVERY = "not applicable: cell discovery request, values not stored"


@dataclass
class Report:
    cells_found: int = 0
    rows_written: int = 0
    requests: int = 0
    runs_fetched: list[str] = field(default_factory=list)
    runs_skipped_existing: list[str] = field(default_factory=list)
    runs_unavailable: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _chunks(seq: list[Any], n: int) -> Iterable[list[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def get_or_create_cell(conn: sqlite3.Connection, model: str, lat: float, lon: float, elev: float | None) -> int:
    lat, lon = round(lat, 6), round(lon, 6)
    row = conn.execute(
        "SELECT cell_id FROM weather_cells WHERE model = ? AND grid_lat = ? AND grid_lon = ?", (model, lat, lon)
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO weather_cells (model, grid_lat, grid_lon, model_elev_m, first_seen_utc) VALUES (?, ?, ?, ?, ?)",
        (model, lat, lon, elev, om.utc_iso(datetime.now(UTC))),
    )
    return int(cur.lastrowid)


def _record_fetch(
    conn: sqlite3.Connection,
    url: str,
    product: str,
    params: dict[str, Any],
    raw_path: Path,
    digest: str,
    issue_time: datetime | None,
    issue_note: str,
    series: list[om.LocationSeries],
) -> int:
    units = series[0].units if series else {}
    missing: dict[str, int] = {}
    for s in series:
        for k, v in s.missing.items():
            missing[k] = missing.get(k, 0) + v
    cur = conn.execute(
        """INSERT INTO weather_fetches (endpoint, product, model, params_json, raw_path, raw_sha256,
            fetched_at_utc, issue_time_utc, issue_time_note, units_json, missing_json, n_locations, variables)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            url,
            product,
            params.get("models", om.MODEL),
            json.dumps(params, sort_keys=True),
            str(raw_path),
            digest,
            om.utc_iso(datetime.now(UTC)),
            om.utc_iso(issue_time) if issue_time else None,
            issue_note,
            json.dumps(units, ensure_ascii=False, sort_keys=True),
            json.dumps(missing, sort_keys=True),
            len(series),
            params.get("hourly"),
        ),
    )
    return int(cur.lastrowid)


def _request(
    fetch: om.Fetcher,
    url: str,
    params: dict[str, Any],
    raw_dir: Path,
    product: str,
    report: Report,
    sleep: Callable[[float], None],
) -> tuple[Any, Path, str]:
    status, body = om.call_with_retry(fetch, url, params, sleep=sleep)
    report.requests += 1
    raw_path, digest = om.save_raw(raw_dir, product, url, params, status, body)
    return body, raw_path, digest


# ---------------------------------------------------------------- cells


def discover_cells(
    conn: sqlite3.Connection,
    fetch: om.Fetcher,
    raw_dir: Path = DEFAULT_RAW_DIR,
    model: str = om.MODEL,
    route_ids: list[str] | None = None,
    batch_size: int = BATCH_SIZE,
    sleep: Callable[[float], None] = time.sleep,
) -> Report:
    """Ask the API which grid cell each route point belongs to.

    We send the route point coordinates (many per request) and read back the
    grid coordinates the API actually used. Distinct grid coordinates are
    distinct cells. Points that already have a cell are skipped, so this is
    cheap to rerun.
    """
    report = Report()
    sql = """SELECT rp.route_id, rp.seq, rp.lat, rp.lon, rp.ele_gpx_m FROM route_points rp
             LEFT JOIN route_point_cells c ON c.route_id = rp.route_id AND c.seq = rp.seq AND c.model = ?
             WHERE c.cell_id IS NULL"""
    args: list[Any] = [model]
    if route_ids:
        sql += f" AND rp.route_id IN ({','.join('?' * len(route_ids))})"
        args += route_ids
    todo = conn.execute(sql + " ORDER BY rp.route_id, rp.seq", args).fetchall()
    before = conn.execute("SELECT COUNT(*) FROM weather_cells WHERE model = ?", (model,)).fetchone()[0]

    for batch in _chunks(todo, batch_size):
        params = {
            "latitude": om.coords_param([r["lat"] for r in batch]),
            "longitude": om.coords_param([r["lon"] for r in batch]),
            "elevation": ",".join(["nan"] * len(batch)),
            "hourly": "temperature_2m",
            "models": model,
            "forecast_hours": 1,
            **om.CELL_PARAMS,
            **om.UNIT_PARAMS,
        }
        body, raw_path, digest = _request(fetch, om.FORECAST_URL, params, raw_dir, "cell_discovery", report, sleep)
        locations = om.as_location_list(body)
        if len(locations) != len(batch):
            raise om.ResponseError(f"asked for {len(batch)} locations, got {len(locations)}")
        series = [om.parse_location(loc, ["temperature_2m"]) for loc in locations]
        with conn:
            _record_fetch(conn, om.FORECAST_URL, "cell_discovery", params, raw_path, digest, None, ISSUE_NOTE_DISCOVERY, series)
            for point, s in zip(batch, series):
                cell_id = get_or_create_cell(conn, model, s.grid_lat, s.grid_lon, s.elevation_m)
                offset = None
                if point["ele_gpx_m"] is not None and s.elevation_m is not None:
                    offset = point["ele_gpx_m"] - s.elevation_m
                conn.execute(
                    """INSERT INTO route_point_cells (route_id, seq, model, cell_id, distance_to_cell_m,
                        ele_offset_gpx_m, method_version) VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(route_id, seq, model) DO UPDATE SET cell_id = excluded.cell_id,
                        distance_to_cell_m = excluded.distance_to_cell_m, ele_offset_gpx_m = excluded.ele_offset_gpx_m,
                        method_version = excluded.method_version""",
                    (
                        point["route_id"],
                        point["seq"],
                        model,
                        cell_id,
                        haversine_m(point["lat"], point["lon"], s.grid_lat, s.grid_lon),
                        offset,
                        CELL_METHOD_VERSION,
                    ),
                )
    after = conn.execute("SELECT COUNT(*) FROM weather_cells WHERE model = ?", (model,)).fetchone()[0]
    report.cells_found = after - before
    return report


@dataclass(frozen=True)
class Cell:
    cell_id: int
    lat: float
    lon: float


def cells_for(conn: sqlite3.Connection, region_ids: list[str] | None = None, model: str = om.MODEL) -> list[Cell]:
    """Unique cells used by the routes of the given regions (all regions if None)."""
    sql = """SELECT DISTINCT wc.cell_id, wc.grid_lat, wc.grid_lon FROM weather_cells wc
             JOIN route_point_cells rpc ON rpc.cell_id = wc.cell_id
             JOIN routes r ON r.route_id = rpc.route_id
             WHERE wc.model = ?"""
    args: list[Any] = [model]
    if region_ids:
        sql += f" AND r.region_id IN ({','.join('?' * len(region_ids))})"
        args += region_ids
    rows = conn.execute(sql + " ORDER BY wc.cell_id", args).fetchall()
    return [Cell(r[0], r[1], r[2]) for r in rows]


def cell_counts_by_region(conn: sqlite3.Connection, model: str = om.MODEL) -> dict[str, int]:
    rows = conn.execute(
        """SELECT r.region_id, COUNT(DISTINCT rpc.cell_id) FROM route_point_cells rpc
           JOIN routes r ON r.route_id = rpc.route_id WHERE rpc.model = ? GROUP BY r.region_id""",
        (model,),
    ).fetchall()
    return {r[0]: r[1] for r in rows}


# ---------------------------------------------------------------- storing values


def store_series(
    conn: sqlite3.Connection,
    cell_id: int,
    model: str,
    series: om.LocationSeries,
    product: str,
    issue_time: datetime | None,
    fetch_id: int,
) -> int:
    """Upsert one cell's hourly values. Returns the number of hours written."""
    cols = [col for _, col in om.VARIABLES.values()]
    var_names = list(om.VARIABLES)
    rows = []
    for i, t in enumerate(series.times_utc):
        lead = (t - issue_time).total_seconds() / 3600 if issue_time else None
        if lead is not None and lead < 0:
            raise om.BadTimestamps(f"valid time {om.utc_iso(t)} is before issue time {om.utc_iso(issue_time)}")
        rows.append(
            (
                cell_id,
                model,
                product,
                om.utc_iso(issue_time) if issue_time else None,
                1 if issue_time else 0,
                om.utc_iso(t),
                lead,
                *[series.values.get(v, [None] * len(series.times_utc))[i] for v in var_names],
                fetch_id,
                SNAPSHOT_METHOD_VERSION,
            )
        )
    updates = ", ".join(f"{c} = excluded.{c}" for c in [*cols, "lead_hours", "fetch_id", "method_version"])
    conn.executemany(
        f"""INSERT INTO forecast_snapshots (cell_id, model, product, issue_time_utc, issue_time_known,
                valid_time_utc, lead_hours, {', '.join(cols)}, fetch_id, method_version)
            VALUES ({', '.join('?' * (9 + len(cols)))})
            ON CONFLICT (cell_id, model, product, issue_key, valid_time_utc) DO UPDATE SET {updates}""",
        rows,
    )
    return len(rows)


def _check_same_cells(cells: list[Cell], series: list[om.LocationSeries]) -> None:
    if len(cells) != len(series):
        raise om.ResponseError(f"asked for {len(cells)} cells, got {len(series)} locations")
    for c, s in zip(cells, series):
        if abs(c.lat - s.grid_lat) > 1e-4 or abs(c.lon - s.grid_lon) > 1e-4:
            raise om.ResponseError(
                f"cell {c.cell_id} drifted: asked ({c.lat}, {c.lon}), API used ({s.grid_lat}, {s.grid_lon})"
            )


def _cell_params(cells: list[Cell], model: str) -> dict[str, Any]:
    return {
        "latitude": om.coords_param([c.lat for c in cells]),
        "longitude": om.coords_param([c.lon for c in cells]),
        "elevation": ",".join(["nan"] * len(cells)),
        "hourly": ",".join(om.VARIABLES),
        "models": model,
        **om.CELL_PARAMS,
        **om.UNIT_PARAMS,
    }


def run_already_stored(conn: sqlite3.Connection, cells: list[Cell], run: datetime, model: str = om.MODEL) -> bool:
    """True when every cell has this run, fetched with every current variable.

    When a variable is added to the collector, older fetches lack it, so the
    run counts as not stored and a rerun fetches it again (an upsert fills
    the new columns without duplicating rows).
    """
    if not cells:
        return True
    ids = [c.cell_id for c in cells]
    rows = conn.execute(
        f"""SELECT f.cell_id, w.variables FROM forecast_snapshots f
            JOIN weather_fetches w ON w.fetch_id = f.fetch_id
            WHERE f.model = ? AND f.product = 'single_run' AND f.issue_time_utc = ?
            AND f.cell_id IN ({','.join('?' * len(ids))})
            GROUP BY f.cell_id""",
        [model, om.utc_iso(run), *ids],
    ).fetchall()
    wanted = set(om.VARIABLES)
    complete = {r[0] for r in rows if r[1] and wanted <= set(r[1].split(","))}
    return len(complete) == len(ids)


def fetch_single_run(
    conn: sqlite3.Connection,
    fetch: om.Fetcher,
    cells: list[Cell],
    run: datetime,
    raw_dir: Path = DEFAULT_RAW_DIR,
    model: str = om.MODEL,
    forecast_hours: int = om.HRDPS_FORECAST_HOURS,
    report: Report | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Report:
    """Fetch one model run for the given cells. Issue time = run time."""
    report = report or Report()
    for batch in _chunks(cells, BATCH_SIZE):
        params = {**_cell_params(batch, model), "run": run.strftime("%Y-%m-%dT%H:%M"), "forecast_hours": forecast_hours}
        body, raw_path, digest = _request(fetch, om.SINGLE_RUNS_URL, params, raw_dir, "single_run", report, sleep)
        series = [om.parse_location(loc) for loc in om.as_location_list(body)]
        _check_same_cells(batch, series)
        with conn:
            fid = _record_fetch(conn, om.SINGLE_RUNS_URL, "single_run", params, raw_path, digest, run, ISSUE_NOTE_SINGLE, series)
            for c, s in zip(batch, series):
                report.rows_written += store_series(conn, c.cell_id, model, s, "single_run", run, fid)
    report.runs_fetched.append(om.utc_iso(run))
    return report


def fetch_stitched(
    conn: sqlite3.Connection,
    fetch: om.Fetcher,
    cells: list[Cell],
    start: date,
    end: date,
    raw_dir: Path = DEFAULT_RAW_DIR,
    model: str = om.MODEL,
    report: Report | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Report:
    """Fetch the stitched archive series (no issue time) for a date range."""
    report = report or Report()
    for batch in _chunks(cells, BATCH_SIZE):
        params = {**_cell_params(batch, model), "start_date": start.isoformat(), "end_date": end.isoformat()}
        body, raw_path, digest = _request(
            fetch, om.HISTORICAL_FORECAST_URL, params, raw_dir, "historical_stitched", report, sleep
        )
        series = [om.parse_location(loc) for loc in om.as_location_list(body)]
        _check_same_cells(batch, series)
        with conn:
            fid = _record_fetch(
                conn, om.HISTORICAL_FORECAST_URL, "historical_stitched", params, raw_path, digest, None, ISSUE_NOTE_STITCHED, series
            )
            for c, s in zip(batch, series):
                report.rows_written += store_series(conn, c.cell_id, model, s, "historical_stitched", None, fid)
    return report


# ---------------------------------------------------------------- collect and backfill


def latest_runs(now: datetime, count: int = 4, run_hours: tuple[int, ...] = om.HRDPS_RUN_HOURS) -> list[datetime]:
    """The ``count`` most recent run times at or before ``now``, newest first."""
    runs = om.run_times_between(now - timedelta(days=2), now, run_hours)
    return sorted(runs, reverse=True)[:count]


def collect_latest(
    conn: sqlite3.Connection,
    fetch: om.Fetcher,
    raw_dir: Path = DEFAULT_RAW_DIR,
    now: datetime | None = None,
    region_ids: list[str] | None = None,
    model: str = om.MODEL,
    sleep: Callable[[float], None] = time.sleep,
) -> Report:
    """Daily job: store the newest published run for every cell.

    Runs appear 1-3 hours after their nominal time, so we try the newest run
    first and step back when the archive says it is not available yet.
    This is what the Mini PC will run on a schedule. No schedule is set up.
    """
    now = now or datetime.now(UTC)
    report = Report()
    cells = cells_for(conn, region_ids, model)
    if not cells:
        report.notes.append("no weather cells yet: load routes and run cell discovery first")
        return report
    for run in latest_runs(now):
        if run_already_stored(conn, cells, run, model):
            report.runs_skipped_existing.append(om.utc_iso(run))
            return report
        try:
            fetch_single_run(conn, fetch, cells, run, raw_dir, model, report=report, sleep=sleep)
            return report
        except om.RunNotAvailable:
            report.runs_unavailable.append(om.utc_iso(run))
    report.errors.append("no recent run was available")
    return report


def backfill(
    conn: sqlite3.Connection,
    fetch: om.Fetcher,
    start: date,
    end: date,
    region_ids: list[str] | None = None,
    raw_dir: Path = DEFAULT_RAW_DIR,
    run_hours: tuple[int, ...] = DEFAULT_BACKFILL_RUN_HOURS,
    include_stitched: bool = True,
    include_runs: bool = True,
    runs_from: date | None = None,
    model: str = om.MODEL,
    sleep: Callable[[float], None] = time.sleep,
) -> Report:
    """Fill a past date range for the cells of some regions.

    * Stitched series: one request per 50 cells for the whole range. Always
      available back to 2023-03-03, but has no issue time.
    * Single runs: one request per run (per 50 cells) for every run hour in
      ``run_hours`` from 2026-04-02 on. Runs already stored are skipped, so a
      rerun costs no extra calls. Days before 2026-04-02 get no true forecast;
      the report says so.
    * ``runs_from`` lets single runs start earlier than ``start``, e.g. the day
      before a trip, which is the forecast a party would have carried.
    """
    report = Report()
    cells = cells_for(conn, region_ids, model)
    if not cells:
        report.notes.append("no weather cells for these regions: load routes and run cell discovery first")
        return report
    if include_stitched:
        if datetime.combine(start, datetime.min.time(), UTC) < om.HISTORICAL_ARCHIVE_START:
            report.notes.append("start is before the HRDPS archive (2023-03-03); API will return gaps or an error")
        fetch_stitched(conn, fetch, cells, start, end, raw_dir, model, report=report, sleep=sleep)
    if include_runs:
        t0 = datetime.combine(runs_from or start, datetime.min.time(), UTC)
        t1 = datetime.combine(end, datetime.min.time(), UTC) + timedelta(hours=23)
        if t0 < om.SINGLE_RUNS_ARCHIVE_START:
            report.notes.append(
                f"{(runs_from or start).isoformat()}..{min(end, om.SINGLE_RUNS_ARCHIVE_START.date() - timedelta(days=1)).isoformat()}: "
                "before the Single Runs archive (2026-04-02); only stitched values with unknown issue time are stored"
            )
            t0 = max(t0, om.SINGLE_RUNS_ARCHIVE_START)
        for run in om.run_times_between(t0, t1, run_hours):
            if run_already_stored(conn, cells, run, model):
                report.runs_skipped_existing.append(om.utc_iso(run))
                continue
            try:
                fetch_single_run(conn, fetch, cells, run, raw_dir, model, report=report, sleep=sleep)
            except om.RunNotAvailable:
                report.runs_unavailable.append(om.utc_iso(run))
            except om.RateLimited as exc:
                report.errors.append(f"rate limited at run {om.utc_iso(run)}: {exc}; rerun later to continue")
                break
    return report


@dataclass(frozen=True)
class BackfillJob:
    label: str
    region_id: str
    start: date
    end: date
    runs_from: date | None = None


def plan_backfill(manifest: dict[str, Any], today: date) -> list[BackfillJob]:
    """Turn the manifest's backfill settings into concrete date ranges.

    "Last N days" means the N whole UTC days ending yesterday. For a single
    trip date, single runs start the day before, so the forecasts that were
    available before the trip are included.
    """
    jobs = []
    region_ids = {r["region_id"] for r in manifest.get("regions", [])}
    for r in manifest.get("regions", []):
        days = r.get("backfill_days")
        if days:
            end = today - timedelta(days=1)
            jobs.append(BackfillJob(f"{r['region_id']} last {days} days", r["region_id"], end - timedelta(days=days - 1), end))
    for route in manifest.get("routes", []):
        for d in route.get("weather_dates", []):
            day = date.fromisoformat(d)
            if route["region_id"] not in region_ids:
                raise ValueError(f"route {route['route_id']} has unknown region")
            jobs.append(BackfillJob(f"{route['route_id']} on {d}", route["region_id"], day, day, day - timedelta(days=1)))
    return jobs
