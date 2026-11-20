"""Response checks: missing values, duplicates, wrong units, bad timestamps.

Uses saved real responses in tests/fixtures/openmeteo/. No network.
"""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mountain_software.weather import openmeteo as om

FIX = Path(__file__).parent / "fixtures" / "openmeteo"


def load(name):
    return json.loads((FIX / name).read_text())


@pytest.fixture
def stitched():
    return om.as_location_list(load("stitched_2_cells_one_day.json"))


def test_real_stitched_response_parses(stitched):
    s = om.parse_location(stitched[0])
    assert len(s.times_utc) == 24
    assert s.times_utc[0] == datetime(2025, 6, 27, 0, tzinfo=UTC)
    assert set(s.values) == set(om.VARIABLES)
    assert s.units["wind_speed_10m"] == "km/h"
    assert s.elevation_m is not None


def test_real_discovery_returns_grid_not_request_coordinates():
    locs = om.as_location_list(load("discovery_3_points.json"))
    series = [om.parse_location(x, ["temperature_2m"]) for x in locs]
    assert len(series) == 3
    # The API answers with grid-cell coordinates, which differ from what we sent.
    assert (series[0].grid_lat, series[0].grid_lon) != (51.41694, -116.21427)
    assert len({(s.grid_lat, s.grid_lon) for s in series}) == 3


def test_missing_values_become_none_and_are_counted(stitched):
    obj = copy.deepcopy(stitched[0])
    obj["hourly"]["wind_gusts_10m"][3] = None
    obj["hourly"]["wind_gusts_10m"][4] = None
    s = om.parse_location(obj)
    assert s.values["wind_gusts_10m"][3] is None
    assert s.missing["wind_gusts_10m"] == 2
    assert s.missing["temperature_2m"] == 0


def test_absent_variable_is_all_missing(stitched):
    obj = copy.deepcopy(stitched[0])
    del obj["hourly"]["snowfall"]
    s = om.parse_location(obj)
    assert s.values["snowfall"] == [None] * 24
    assert s.missing["snowfall"] == 24


@pytest.mark.parametrize("var,bad_unit", [("wind_speed_10m", "mph"), ("temperature_2m", "°F"), ("snowfall", "inch"), ("wind_gusts_10m", None)])
def test_wrong_units_are_rejected(stitched, var, bad_unit):
    obj = copy.deepcopy(stitched[0])
    obj["hourly_units"][var] = bad_unit
    with pytest.raises(om.UnitMismatch):
        om.parse_location(obj)


def test_duplicate_timestamps_rejected(stitched):
    obj = copy.deepcopy(stitched[0])
    obj["hourly"]["time"][5] = obj["hourly"]["time"][4]
    with pytest.raises(om.BadTimestamps, match="duplicate"):
        om.parse_location(obj)


def test_gap_or_backwards_time_rejected(stitched):
    obj = copy.deepcopy(stitched[0])
    obj["hourly"]["time"][10], obj["hourly"]["time"][11] = obj["hourly"]["time"][11], obj["hourly"]["time"][10]
    with pytest.raises(om.BadTimestamps, match="hourly"):
        om.parse_location(obj)


@pytest.mark.parametrize("bad", ["2025-06-27 00:00", "27/06/2025 00:00", "", None, "2025-06-27T25:00"])
def test_unreadable_time_rejected(stitched, bad):
    obj = copy.deepcopy(stitched[0])
    obj["hourly"]["time"][0] = bad
    with pytest.raises(om.BadTimestamps):
        om.parse_location(obj)


def test_non_utc_response_rejected(stitched):
    obj = copy.deepcopy(stitched[0])
    obj["utc_offset_seconds"] = -21600
    obj["timezone"] = "America/Edmonton"
    with pytest.raises(om.BadTimestamps, match="UTC"):
        om.parse_location(obj)


def test_unix_time_format_rejected(stitched):
    obj = copy.deepcopy(stitched[0])
    obj["hourly_units"]["time"] = "unixtime"
    with pytest.raises(om.BadTimestamps):
        om.parse_location(obj)


def test_length_mismatch_and_text_values_rejected(stitched):
    obj = copy.deepcopy(stitched[0])
    obj["hourly"]["precipitation"] = obj["hourly"]["precipitation"][:-1]
    with pytest.raises(om.ResponseError, match="values for"):
        om.parse_location(obj)
    obj = copy.deepcopy(stitched[0])
    obj["hourly"]["precipitation"][0] = "0.2"
    with pytest.raises(om.ResponseError, match="non-numeric"):
        om.parse_location(obj)


def test_api_error_messages_map_to_exceptions():
    with pytest.raises(om.RateLimited):
        om.raise_for_api_error(429, {"error": True, "reason": "Daily API request limit exceeded. Please try again tomorrow."})
    with pytest.raises(om.RunNotAvailable):
        om.raise_for_api_error(400, {"error": True, "reason": "The requested model run is not available. Model: cmc_gem_hrdps"})
    with pytest.raises(om.OpenMeteoError):
        om.raise_for_api_error(400, {"error": True, "reason": "Cannot initialize WeatherVariable"})
    om.raise_for_api_error(200, {"latitude": 1})


def test_retry_waits_then_succeeds():
    answers = [(429, {"error": True, "reason": "Daily API request limit exceeded."}), (200, {"ok": 1})]
    waits = []
    status, body = om.call_with_retry(lambda u, p: answers.pop(0), "u", {}, sleep=waits.append)
    assert body == {"ok": 1} and len(waits) == 1


def test_retry_does_not_repeat_missing_runs():
    calls = []

    def fetch(u, p):
        calls.append(1)
        return 400, {"error": True, "reason": "The requested model run is not available."}

    with pytest.raises(om.RunNotAvailable):
        om.call_with_retry(fetch, "u", {}, sleep=lambda s: None)
    assert len(calls) == 1


def test_run_times_between():
    runs = om.run_times_between(datetime(2026, 10, 15, 6, tzinfo=UTC), datetime(2026, 10, 16, 6, tzinfo=UTC))
    assert [r.hour for r in runs] == [6, 12, 18, 0, 6]


def test_real_single_run_first_hour_accumulations_are_missing():
    """Real behaviour seen on 2026-11-18: at lead hour 0 a run has no
    'preceding hour' total yet, so precipitation and snowfall are null."""
    locs = om.as_location_list(load("single_run_2_cells.json"))
    s = om.parse_location(locs[0])
    assert s.times_utc[0] == datetime(2026, 10, 15, 12, tzinfo=UTC)
    assert s.values["precipitation"][0] is None and s.values["snowfall"][0] is None
    assert s.missing["precipitation"] == 1
    assert s.values["temperature_2m"][0] is not None
