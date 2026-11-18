"""Check model weather against real weather stations.

A weather model is a guess; a station is a measurement at one spot. Before
trusting model wind on the peaks, compare it with stations near them,
especially ridge-top stations, which feel the same wind that moves snow.

Source: Avalanche Canada's public weather API (no key needed), which relays
Parks Canada and Kananaskis Country stations. Terms: Avalanche Canada's terms
of use do not allow reproducing their material without consent. So raw
station data stays in git-ignored ``data/raw/`` and the database; only
summary statistics (bias, error, correlation) are published.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from ..geo import angular_difference_deg
from ..weather import collector as col
from ..weather import openmeteo as om

AVCAN_BASE = "https://weather.prod.avalanche.ca"
MAX_DAYS_PER_REQUEST = 31

# Stations chosen per region (see docs/stations.md for the search and why).
STATIONS = [
    {"station_id": 111, "name": "Bosworth Upper", "region_id": "lake_louise", "role": "ridge-top wind and temperature"},
    {"station_id": 129, "name": "Tangle Ridge", "region_id": "icefield", "role": "ridge-top wind and temperature"},
    {"station_id": 1, "name": "Burstall Pass", "region_id": "burstall", "role": "on-site wind, temperature, snow depth"},
]

METHOD_VERSION = "station-compare-v1"


def _fetch_json(url: str, params: dict[str, Any] | None = None, timeout_s: float = 60.0) -> Any:
    import requests

    r = requests.get(url, params=params, timeout=timeout_s, headers={"User-Agent": "mountain-software research"})
    r.raise_for_status()
    return r.json()


def station_metadata(fetch_json: Callable[..., Any] = _fetch_json) -> dict[int, dict]:
    return {s["stationId"]: s for s in fetch_json(f"{AVCAN_BASE}/stations")}


def parse_measurement_time(text: str) -> datetime:
    """AvCan times look like '2026-11-08T03:00:00Z' (UTC)."""
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def store_station(conn: sqlite3.Connection, meta: dict) -> None:
    with conn:
        conn.execute(
            """INSERT INTO stations (station_id, network, name, lat, lon, elev_m, source, external_id)
               VALUES (?, 'avalanche_canada', ?, ?, ?, ?, ?, ?)
               ON CONFLICT(station_id) DO UPDATE SET name = excluded.name, lat = excluded.lat, lon = excluded.lon,
               elev_m = excluded.elev_m, source = excluded.source, external_id = excluded.external_id""",
            (meta["stationId"], meta["name"], meta["latitude"], meta["longitude"], meta.get("elevation"),
             meta.get("source"), meta.get("externalId")),
        )


def fetch_measurements(
    conn: sqlite3.Connection,
    station_id: int,
    start: date,
    end: date,
    raw_dir: Path = Path("data/raw"),
    fetch_json: Callable[..., Any] = _fetch_json,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Download hourly measurements in chunks of up to 31 days and upsert them."""
    n = 0
    day = start
    while day <= end:
        chunk_end = min(end, day + timedelta(days=MAX_DAYS_PER_REQUEST - 1))
        params = {"fromDate": f"{day.isoformat()}T00:00:00Z", "toDate": f"{chunk_end.isoformat()}T23:00:00Z"}
        body = fetch_json(f"{AVCAN_BASE}/stations/{station_id}/measurements", params)
        folder = raw_dir / "avcan" / str(station_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{day.isoformat()}_{chunk_end.isoformat()}.json").write_text(json.dumps(body))
        rows = []
        for m in body:
            t = parse_measurement_time(m["measurementDateTime"])
            rows.append((
                station_id, t.strftime("%Y-%m-%dT%H:%M:%SZ"), m.get("airTempAvg"), m.get("windSpeedAvg"),
                m.get("windDirAvg"), m.get("windSpeedGust"), m.get("relativeHumidity"), m.get("snowHeight"),
            ))
        with conn:
            conn.executemany(
                """INSERT INTO station_obs (station_id, valid_time_utc, air_temp_c, wind_speed_kmh, wind_from_deg,
                    wind_gust_kmh, rel_humidity, snow_height_cm) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(station_id, valid_time_utc) DO UPDATE SET air_temp_c = excluded.air_temp_c,
                    wind_speed_kmh = excluded.wind_speed_kmh, wind_from_deg = excluded.wind_from_deg,
                    wind_gust_kmh = excluded.wind_gust_kmh, rel_humidity = excluded.rel_humidity,
                    snow_height_cm = excluded.snow_height_cm""",
                rows,
            )
        n += len(rows)
        day = chunk_end + timedelta(days=1)
        sleep(1.0)
    return n


def station_cell(
    conn: sqlite3.Connection,
    station_id: int,
    fetch: om.Fetcher,
    raw_dir: Path = Path("data/raw"),
    model: str = om.MODEL,
) -> col.Cell:
    """Find (and remember) the model cell that contains a station."""
    row = conn.execute(
        """SELECT wc.cell_id, wc.grid_lat, wc.grid_lon FROM station_cells sc JOIN weather_cells wc USING (cell_id)
           WHERE sc.station_id = ? AND sc.model = ?""",
        (station_id, model),
    ).fetchone()
    if row:
        return col.Cell(row[0], row[1], row[2])
    st = conn.execute("SELECT lat, lon FROM stations WHERE station_id = ?", (station_id,)).fetchone()
    params = {
        "latitude": f"{st[0]:.6f}", "longitude": f"{st[1]:.6f}", "elevation": "nan", "hourly": "temperature_2m",
        "models": model, "forecast_hours": 1, **om.CELL_PARAMS, **om.UNIT_PARAMS,
    }
    status, body = om.call_with_retry(fetch, om.FORECAST_URL, params)
    om.save_raw(raw_dir, "cell_discovery", om.FORECAST_URL, params, status, body)
    s = om.parse_location(om.as_location_list(body)[0], ["temperature_2m"])
    with conn:
        cell_id = col.get_or_create_cell(conn, model, s.grid_lat, s.grid_lon, s.elevation_m)
        conn.execute(
            "INSERT INTO station_cells (station_id, model, cell_id) VALUES (?, ?, ?)", (station_id, model, cell_id)
        )
    return col.Cell(cell_id, round(s.grid_lat, 6), round(s.grid_lon, 6))


@dataclass
class Comparison:
    station_id: int
    variable: str
    model_variable: str
    n: int
    bias: float | None
    mae: float | None
    rmse: float | None
    corr: float | None
    station_mean: float | None
    model_mean: float | None
    note: str = ""


def _stats(obs: list[float], mod: list[float]) -> tuple:
    a, b = np.array(obs, float), np.array(mod, float)
    d = b - a
    corr = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 and a.std() > 0 and b.std() > 0 else None
    return float(d.mean()), float(np.abs(d).mean()), float(math.sqrt((d**2).mean())), corr, float(a.mean()), float(b.mean())


def compare(
    conn: sqlite3.Connection,
    station_id: int,
    start: datetime,
    end: datetime,
    product: str = "historical_stitched",
    model: str = om.MODEL,
    cell_id: int | None = None,
) -> list[Comparison]:
    """Station vs model statistics for wind speed, wind direction and temperature.

    Pairs are matched on the same UTC hour. Direction is compared only when
    the station wind is at least 10 km/h (calm directions are noise), using
    the circular difference. Bias = model minus station.
    """
    cell = cell_id
    if cell is None:
        cell = conn.execute(
            "SELECT cell_id FROM station_cells WHERE station_id = ? AND model = ?", (station_id, model)
        ).fetchone()[0]
    rows = conn.execute(
        """SELECT s.air_temp_c, s.wind_speed_kmh, s.wind_from_deg,
                  f.temperature_2m_c, f.wind_speed_10m_kmh, f.wind_direction_10m_deg,
                  f.wind_speed_700hpa_kmh, f.wind_direction_700hpa_deg, f.temperature_700hpa_c
           FROM station_obs s JOIN forecast_snapshots f
             ON f.valid_time_utc = s.valid_time_utc AND f.cell_id = ? AND f.product = ? AND f.model = ?
           WHERE s.station_id = ? AND s.valid_time_utc >= ? AND s.valid_time_utc <= ?""",
        (cell, product, model, station_id, start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")),
    ).fetchall()
    out = []
    pairs = {
        ("wind_speed_kmh", "wind_speed_10m_kmh"): (1, 4),
        ("wind_speed_kmh", "wind_speed_700hpa_kmh"): (1, 6),
        ("air_temp_c", "temperature_2m_c"): (0, 3),
        ("air_temp_c", "temperature_700hpa_c"): (0, 8),
    }
    for (sv, mv), (i, j) in pairs.items():
        ok = [(r[i], r[j]) for r in rows if r[i] is not None and r[j] is not None]
        if not ok:
            out.append(Comparison(station_id, sv, mv, 0, None, None, None, None, None, None))
            continue
        out.append(Comparison(station_id, sv, mv, len(ok), *_stats([a for a, _ in ok], [b for _, b in ok])))
    for mv, (k, j) in {"wind_direction_10m_deg": (2, 5), "wind_direction_700hpa_deg": (2, 7)}.items():
        ok = [(r[k], r[j]) for r in rows if r[k] is not None and r[j] is not None and (r[1] or 0) >= 10]
        diffs = [angular_difference_deg(a, b) for a, b in ok]
        out.append(Comparison(
            station_id, "wind_from_deg", mv, len(ok), None,
            float(np.mean(diffs)) if diffs else None, None, None, None, None,
            note="mae = mean circular difference (deg), station wind >= 10 km/h",
        ))
    return out
