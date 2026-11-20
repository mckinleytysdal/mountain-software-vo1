"""A pretend Open-Meteo for tests: answers like the real API, offline.

Grid: cells every 0.025 degrees, so nearby route points share a cell. Values
are made up but deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from mountain_software.weather import openmeteo as om

GRID = 0.025


def snap(v: float) -> float:
    return round(round(v / GRID) * GRID, 6)


class FakeOpenMeteo:
    def __init__(self, unavailable_runs=(), rate_limit_after=None, units_override=None):
        self.calls: list[tuple[str, dict]] = []
        self.unavailable_runs = set(unavailable_runs)
        self.rate_limit_after = rate_limit_after
        self.units_override = units_override or {}

    def __call__(self, url: str, params: dict):
        self.calls.append((url, dict(params)))
        if self.rate_limit_after is not None and len(self.calls) > self.rate_limit_after:
            return 429, {"error": True, "reason": "Daily API request limit exceeded. Please try again tomorrow."}
        lats = [float(x) for x in str(params["latitude"]).split(",")]
        lons = [float(x) for x in str(params["longitude"]).split(",")]
        variables = params["hourly"].split(",")
        if url == om.SINGLE_RUNS_URL:
            if params["run"] in self.unavailable_runs:
                return 400, {"error": True, "reason": f"The requested model run is not available. Model: cmc_gem_hrdps, run: {params['run']}Z"}
            t0 = datetime.strptime(params["run"], "%Y-%m-%dT%H:%M")
            n = int(params.get("forecast_hours", 48))
        elif url == om.HISTORICAL_FORECAST_URL:
            t0 = datetime.fromisoformat(params["start_date"])
            n = ((datetime.fromisoformat(params["end_date"]) - t0).days + 1) * 24
        else:
            t0 = datetime(2026, 11, 18, 9)
            n = int(params.get("forecast_hours", 1))
        times = [(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n)]
        out = []
        for la, lo in zip(lats, lons):
            g_la, g_lo = snap(la), snap(lo)
            hourly = {"time": times}
            for k, v in enumerate(variables):
                base = 3000.0 if v.startswith("geopotential") else 0.0
                hourly[v] = [round(base + k + i * 0.1 + g_la - 51, 2) for i in range(n)]
            units = {v: om.VARIABLES[v][0] for v in variables}
            units.update(self.units_override)
            out.append({
                "latitude": g_la, "longitude": g_lo, "elevation": 2000.0 + 100 * (g_la - 51.4) / GRID,
                "utc_offset_seconds": 0, "timezone": "GMT", "timezone_abbreviation": "GMT",
                "hourly_units": {"time": "iso8601", **units}, "hourly": hourly,
            })
        return 200, out if len(out) > 1 else out[0]
