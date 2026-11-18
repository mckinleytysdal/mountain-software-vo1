"""Talk to Open-Meteo and check what comes back.

Three Open-Meteo services are used (checked against the docs on 2026-11-18,
see docs/weather-data.md):

* Forecast API (``api.open-meteo.com``): the newest forecast. Used here only
  to discover which model grid cell each route point falls in.
* Single Runs API (``single-runs-api.open-meteo.com``): one specific model run,
  chosen with ``run=YYYY-MM-DDTHH:MM`` (UTC). The run time IS the forecast
  issue time, so these are true forecasts. Archive starts 2026-04-02.
* Historical Forecast API (``historical-forecast-api.open-meteo.com``): the
  first hours of every run stitched into one continuous series. Goes back to
  2023-03-03 for HRDPS, but it does NOT say which run each hour came from, so
  we store no issue time and never call these values forecasts.

Analogy: a single run is one guidebook edition with a printed date. The
stitched series is a scrapbook of the first page of every edition; useful,
but you cannot tell which edition a page came from.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

MODEL = "gem_hrdps_continental"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SINGLE_RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

SINGLE_RUNS_ARCHIVE_START = datetime(2026, 4, 2, tzinfo=UTC)
HISTORICAL_ARCHIVE_START = datetime(2023, 3, 3, tzinfo=UTC)
HRDPS_RUN_HOURS = (0, 6, 12, 18)
HRDPS_FORECAST_HOURS = 48

# Open-Meteo variable name -> (unit string the API must report, database column)
VARIABLES: dict[str, tuple[str, str]] = {
    "temperature_2m": ("°C", "temperature_2m_c"),
    "wind_speed_10m": ("km/h", "wind_speed_10m_kmh"),
    "wind_direction_10m": ("°", "wind_direction_10m_deg"),
    "wind_gusts_10m": ("km/h", "wind_gusts_10m_kmh"),
    "snowfall": ("cm", "snowfall_cm"),
    "precipitation": ("mm", "precipitation_mm"),
    # Free-atmosphere wind at the 700 hPa pressure level, about 3,000 m above
    # sea level here: close to ridge-top height, and not slowed by the smooth
    # model surface. Forecasters use ridge-top wind to judge snow transport.
    "wind_speed_700hPa": ("km/h", "wind_speed_700hpa_kmh"),
    "wind_direction_700hPa": ("°", "wind_direction_700hpa_deg"),
    "geopotential_height_700hPa": ("m", "geopotential_height_700hpa_m"),
    "temperature_700hPa": ("°C", "temperature_700hpa_c"),
}

# Ask for the units explicitly, so a change of API default cannot slip through.
UNIT_PARAMS = {
    "temperature_unit": "celsius",
    "wind_speed_unit": "kmh",
    "precipitation_unit": "mm",
    "timezone": "GMT",
}

# Raw model values: nearest grid cell, no elevation downscaling. With
# elevation=nan the API returns the model cell's own elevation.
CELL_PARAMS = {"cell_selection": "nearest"}


class OpenMeteoError(RuntimeError):
    """The API answered with an error."""


class RateLimited(OpenMeteoError):
    """Too many calls: wait and retry later."""


class RunNotAvailable(OpenMeteoError):
    """That model run is not in the archive (too old, or not published yet)."""


class ResponseError(ValueError):
    """The response failed a data check (units, timestamps, shape)."""


class UnitMismatch(ResponseError):
    pass


class BadTimestamps(ResponseError):
    pass


# A fetcher takes (url, params) and returns (HTTP status, parsed JSON).
Fetcher = Callable[[str, dict[str, Any]], tuple[int, Any]]


def http_fetcher(timeout_s: float = 60.0) -> Fetcher:
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = "mountain-software research pipeline (non-commercial)"

    def fetch(url: str, params: dict[str, Any]) -> tuple[int, Any]:
        resp = session.get(url, params=params, timeout=timeout_s)
        try:
            body = resp.json()
        except ValueError:
            body = {"error": True, "reason": f"non-JSON response: {resp.text[:200]}"}
        return resp.status_code, body

    return fetch


def raise_for_api_error(status: int, body: Any) -> None:
    if isinstance(body, dict) and body.get("error"):
        reason = str(body.get("reason", "unknown error"))
        low = reason.lower()
        if "limit exceeded" in low or "too many" in low or status == 429:
            raise RateLimited(reason)
        if "run is not available" in low:
            raise RunNotAvailable(reason)
        raise OpenMeteoError(reason)
    if status >= 400:
        raise OpenMeteoError(f"HTTP {status}")


def call_with_retry(
    fetch: Fetcher,
    url: str,
    params: dict[str, Any],
    attempts: int = 4,
    backoff_s: float = 20.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, Any]:
    """Call the API, waiting and retrying when it says we are rate limited.

    Other errors are raised at once: retrying a run that does not exist
    would only burn more of the daily allowance.
    """
    for attempt in range(1, attempts + 1):
        try:
            status, body = fetch(url, params)
        except OSError as exc:  # network trouble (requests' errors subclass OSError)
            if attempt == attempts:
                raise OpenMeteoError(f"network error: {exc}") from exc
            sleep(backoff_s * attempt)
            continue
        try:
            raise_for_api_error(status, body)
            return status, body
        except RateLimited:
            if attempt == attempts:
                raise
            sleep(backoff_s * attempt)
    raise AssertionError("unreachable")


@dataclass
class LocationSeries:
    """One location's hourly series, checked and converted to UTC."""

    grid_lat: float
    grid_lon: float
    elevation_m: float | None
    times_utc: list[datetime]
    values: dict[str, list[float | None]]
    units: dict[str, str]
    missing: dict[str, int] = field(default_factory=dict)


def as_location_list(body: Any) -> list[dict[str, Any]]:
    """Open-Meteo returns one object for one location and a list for several."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        return [body]
    raise ResponseError(f"unexpected response type {type(body).__name__}")


def parse_time_utc(text: str) -> datetime:
    """Parse an Open-Meteo time like '2026-11-18T06:00' that is already in GMT."""
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError) as exc:
        raise BadTimestamps(f"unreadable time {text!r}") from exc
    return dt.replace(tzinfo=UTC)


def parse_location(obj: dict[str, Any], variables: list[str] | None = None) -> LocationSeries:
    """Check one location's response and return a tidy :class:`LocationSeries`.

    Checks, in order:
    1. the response is in GMT (utc_offset_seconds == 0), so times are UTC;
    2. every requested variable reports the expected unit;
    3. timestamps parse, have no duplicates, increase, and are exactly hourly;
    4. every value array has one value per timestamp.
    Missing values (JSON null) are allowed; they become None and are counted.
    A variable absent from the response is treated as all-missing.
    """
    variables = variables or list(VARIABLES)
    if obj.get("utc_offset_seconds", 0) != 0 or obj.get("timezone", "GMT") not in ("GMT", "UTC"):
        raise BadTimestamps(f"response not in UTC: timezone={obj.get('timezone')} offset={obj.get('utc_offset_seconds')}")
    hourly = obj.get("hourly")
    units = obj.get("hourly_units", {})
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise ResponseError("response has no hourly block")

    for var in variables:
        if var in hourly:
            expected = VARIABLES[var][0]
            got = units.get(var)
            if got != expected:
                raise UnitMismatch(f"{var}: expected unit {expected!r}, got {got!r}")
    if units.get("time", "iso8601") != "iso8601":
        raise BadTimestamps(f"time format is {units.get('time')!r}, expected 'iso8601'")

    times = [parse_time_utc(t) for t in hourly["time"]]
    if len(set(times)) != len(times):
        raise BadTimestamps("duplicate timestamps in response")
    for a, b in zip(times, times[1:]):
        if b - a != timedelta(hours=1):
            raise BadTimestamps(f"times not hourly and increasing: {a.isoformat()} then {b.isoformat()}")

    values: dict[str, list[float | None]] = {}
    missing: dict[str, int] = {}
    for var in variables:
        arr = hourly.get(var)
        if arr is None:
            arr = [None] * len(times)
        if len(arr) != len(times):
            raise ResponseError(f"{var}: {len(arr)} values for {len(times)} times")
        clean: list[float | None] = []
        for v in arr:
            if v is None:
                clean.append(None)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                clean.append(float(v))
            else:
                raise ResponseError(f"{var}: non-numeric value {v!r}")
        values[var] = clean
        missing[var] = sum(1 for v in clean if v is None)

    return LocationSeries(
        grid_lat=float(obj["latitude"]),
        grid_lon=float(obj["longitude"]),
        elevation_m=float(obj["elevation"]) if obj.get("elevation") is not None else None,
        times_utc=times,
        values=values,
        units={v: units.get(v, "") for v in variables if v in units},
        missing=missing,
    )


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_raw(raw_dir: Path, product: str, url: str, params: dict[str, Any], status: int, body: Any) -> tuple[Path, str]:
    """Write the untouched response (plus what we asked for) to data/raw/.

    Returns the file path and its SHA-256 fingerprint.
    """
    fetched = datetime.now(UTC)
    payload = {
        "request": {"url": url, "params": params},
        "fetched_at_utc": utc_iso(fetched),
        "http_status": status,
        "response": body,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(text.encode()).hexdigest()
    folder = raw_dir / "openmeteo" / product / fetched.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{fetched.strftime('%H%M%S')}_{digest[:12]}.json"
    path.write_text(text)
    return path, digest


def coords_param(values: list[float]) -> str:
    return ",".join(f"{v:.6f}" for v in values)


def run_times_between(start: datetime, end: datetime, run_hours: tuple[int, ...] = HRDPS_RUN_HOURS) -> list[datetime]:
    """Every model run time (UTC) from ``start`` to ``end`` inclusive."""
    out = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= end:
        for h in run_hours:
            t = day.replace(hour=h)
            if start <= t <= end:
                out.append(t)
        day += timedelta(days=1)
    return out
