"""Collector and backfill logic against the offline fake API."""

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from fake_openmeteo import FakeOpenMeteo
from gpx_factory import gpx_from_points, straight_line_points
from mountain_software.routes import load_all
from mountain_software.weather import collector as col
from mountain_software.weather import openmeteo as om

MANIFEST = """
[[regions]]
region_id = "lake_louise"
name = "Lake Louise"
backfill_days = 90

[[regions]]
region_id = "burstall"
name = "Burstall"
backfill_days = 30

[[routes]]
route_id = "line_a"
name = "Line A"
region_id = "lake_louise"
route_shape = "one_way"
file = "own/a.gpx"
source = "synthetic"
download_date = "2026-11-18"
terms_note = "test"
weather_dates = ["2026-10-16"]

[[routes]]
route_id = "line_b"
name = "Line B"
region_id = "burstall"
route_shape = "one_way"
file = "own/b.gpx"
source = "synthetic"
download_date = "2026-11-18"
terms_note = "test"
weather_dates = ["2025-06-27"]
"""

NO_SLEEP = lambda s: None  # noqa: E731


@pytest.fixture
def loaded(conn, tmp_path):
    (tmp_path / "own").mkdir()
    # 6 km due north from 51.40: crosses several 0.025 degree fake cells.
    (tmp_path / "own/a.gpx").write_text(gpx_from_points(straight_line_points(6000, 50, lat0=51.40, lon0=-116.30)))
    (tmp_path / "own/b.gpx").write_text(gpx_from_points(straight_line_points(1000, 50, lat0=50.70, lon0=-115.30)))
    (tmp_path / "manifest.toml").write_text(MANIFEST)
    load_all(conn, tmp_path / "manifest.toml")
    return conn


@pytest.fixture
def raw_dir(tmp_path):
    return tmp_path / "raw"


def test_discover_cells_dedupes_and_records_offsets(loaded, raw_dir):
    api = FakeOpenMeteo()
    rep = col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    counts = col.cell_counts_by_region(loaded)
    assert counts["lake_louise"] == 3  # 51.400 .. 51.454 snaps to 51.40, 51.425, 51.45
    assert counts["burstall"] == 1
    assert rep.cells_found == 4
    n_points = loaded.execute("SELECT COUNT(*) FROM route_points").fetchone()[0]
    assert loaded.execute("SELECT COUNT(*) FROM route_point_cells").fetchone()[0] == n_points
    assert loaded.execute("SELECT COUNT(*) FROM route_point_cells WHERE ele_offset_gpx_m IS NULL").fetchone()[0] == 0
    # Rerun: nothing left to discover, no API calls.
    before = len(api.calls)
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    assert len(api.calls) == before


def test_each_cell_fetched_once_per_run(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    api.calls.clear()
    run = datetime(2026, 10, 15, 12, tzinfo=UTC)
    col.fetch_single_run(loaded, api, col.cells_for(loaded), run, raw_dir, sleep=NO_SLEEP)
    assert len(api.calls) == 1
    lats = api.calls[0][1]["latitude"].split(",")
    assert len(lats) == len(set(lats)) == 4


def test_single_run_rows_have_issue_valid_and_lead(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    run = datetime(2026, 10, 15, 12, tzinfo=UTC)
    col.fetch_single_run(loaded, api, col.cells_for(loaded), run, raw_dir, sleep=NO_SLEEP)
    rows = loaded.execute(
        "SELECT issue_time_utc, valid_time_utc, lead_hours, issue_time_known FROM forecast_snapshots ORDER BY valid_time_utc"
    ).fetchall()
    assert len(rows) == 4 * 48
    assert {r["issue_time_utc"] for r in rows} == {"2026-10-15T12:00:00Z"}
    assert rows[0]["valid_time_utc"] == "2026-10-15T12:00:00Z" and rows[0]["lead_hours"] == 0
    assert max(r["lead_hours"] for r in rows) == 47
    assert all(r["issue_time_known"] == 1 for r in rows)


def test_collector_twice_makes_no_duplicates(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    now = datetime(2026, 11, 18, 9, 30, tzinfo=UTC)
    r1 = col.collect_latest(loaded, api, raw_dir, now=now, sleep=NO_SLEEP)
    n1 = loaded.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()[0]
    calls = len(api.calls)
    r2 = col.collect_latest(loaded, api, raw_dir, now=now, sleep=NO_SLEEP)
    assert r1.runs_fetched == ["2026-11-18T06:00:00Z"]
    assert r2.runs_skipped_existing == ["2026-11-18T06:00:00Z"]
    assert loaded.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()[0] == n1
    assert len(api.calls) == calls  # second run spends no API calls


def test_forced_refetch_updates_not_duplicates(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    run = datetime(2026, 10, 15, 12, tzinfo=UTC)
    cells = col.cells_for(loaded)
    col.fetch_single_run(loaded, api, cells, run, raw_dir, sleep=NO_SLEEP)
    col.fetch_single_run(loaded, api, cells, run, raw_dir, sleep=NO_SLEEP)
    col.fetch_stitched(loaded, api, cells, date(2026, 10, 15), date(2026, 10, 15), raw_dir, sleep=NO_SLEEP)
    col.fetch_stitched(loaded, api, cells, date(2026, 10, 15), date(2026, 10, 15), raw_dir, sleep=NO_SLEEP)
    by_product = dict(loaded.execute("SELECT product, COUNT(*) FROM forecast_snapshots GROUP BY product").fetchall())
    assert by_product == {"single_run": 4 * 48, "historical_stitched": 4 * 24}


def test_collect_steps_back_when_newest_run_not_published(loaded, raw_dir):
    api = FakeOpenMeteo(unavailable_runs={"2026-11-18T06:00"})
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    rep = col.collect_latest(loaded, api, raw_dir, now=datetime(2026, 11, 18, 7, tzinfo=UTC), sleep=NO_SLEEP)
    assert rep.runs_unavailable == ["2026-11-18T06:00:00Z"]
    assert rep.runs_fetched == ["2026-11-18T00:00:00Z"]


def test_stitched_values_have_no_issue_time(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    rep = col.backfill(loaded, api, date(2025, 6, 27), date(2025, 6, 27), ["burstall"], raw_dir, sleep=NO_SLEEP)
    rows = loaded.execute("SELECT DISTINCT product, issue_time_utc, issue_time_known, lead_hours FROM forecast_snapshots").fetchall()
    assert [tuple(r) for r in rows] == [("historical_stitched", None, 0, None)]
    assert any("before the Single Runs archive" in n for n in rep.notes)
    assert not any(url == om.SINGLE_RUNS_URL for url, _ in api.calls)
    note = loaded.execute("SELECT issue_time_note FROM weather_fetches WHERE product = 'historical_stitched'").fetchone()[0]
    assert "not a true forecast" in note


def test_database_refuses_stitched_row_with_issue_time(loaded):
    loaded.execute("INSERT INTO weather_cells (model, grid_lat, grid_lon, first_seen_utc) VALUES ('m', 1, 1, 'x')")
    loaded.execute(
        "INSERT INTO weather_fetches (endpoint, product, model, params_json, raw_path, raw_sha256, fetched_at_utc, issue_time_note, n_locations)"
        " VALUES ('e', 'p', 'm', '{}', 'r', 'h', 'x', 'n', 1)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        loaded.execute(
            "INSERT INTO forecast_snapshots (cell_id, model, product, issue_time_utc, issue_time_known, valid_time_utc,"
            " lead_hours, fetch_id, method_version) VALUES (1, 'm', 'historical_stitched', '2026-01-01T00:00:00Z', 1, 'x', 0, 1, 'v')"
        )


def test_backfill_single_date_includes_day_before_runs(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    job = [j for j in col.plan_backfill({"regions": [{"region_id": "lake_louise", "name": "x"}],
            "routes": [{"route_id": "line_a", "region_id": "lake_louise", "weather_dates": ["2026-10-16"]}]}, date(2026, 11, 18))][0]
    rep = col.backfill(loaded, api, job.start, job.end, [job.region_id], raw_dir, runs_from=job.runs_from, sleep=NO_SLEEP)
    assert rep.runs_fetched == ["2026-10-15T00:00:00Z", "2026-10-15T12:00:00Z", "2026-10-16T00:00:00Z", "2026-10-16T12:00:00Z"]
    # Rerun: everything is already stored, so only the cheap stitched call repeats.
    api.calls.clear()
    rep2 = col.backfill(loaded, api, job.start, job.end, [job.region_id], raw_dir, runs_from=job.runs_from, sleep=NO_SLEEP)
    assert len(rep2.runs_skipped_existing) == 4 and not rep2.runs_fetched
    assert [u for u, _ in api.calls] == [om.HISTORICAL_FORECAST_URL]


def test_backfill_stops_cleanly_when_rate_limited(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    api.rate_limit_after = len(api.calls) + 3  # stitched + 2 runs, then refuse
    rep = col.backfill(loaded, api, date(2026, 10, 1), date(2026, 10, 10), ["lake_louise"], raw_dir, sleep=NO_SLEEP)
    assert len(rep.runs_fetched) == 2
    assert rep.errors and "rerun later" in rep.errors[0]


def test_plan_backfill_windows():
    manifest = {
        "regions": [
            {"region_id": "icefield", "name": "i", "backfill_days": 30},
            {"region_id": "burstall", "name": "b", "backfill_days": 30},
            {"region_id": "lake_louise", "name": "l", "backfill_days": 90},
        ],
        "routes": [
            {"route_id": "silverhorn", "region_id": "icefield", "weather_dates": ["2025-06-27"]},
            {"route_id": "north_victoria", "region_id": "lake_louise", "weather_dates": ["2026-10-16"]},
        ],
    }
    jobs = {j.label: j for j in col.plan_backfill(manifest, date(2026, 11, 18))}
    assert jobs["icefield last 30 days"].start == date(2026, 10, 19)
    assert jobs["icefield last 30 days"].end == date(2026, 11, 17)
    assert (jobs["lake_louise last 90 days"].end - jobs["lake_louise last 90 days"].start).days == 89
    assert jobs["silverhorn on 2025-06-27"].runs_from == date(2025, 6, 26)
    assert len(jobs) == 5


def test_raw_responses_saved_with_request(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    files = list(raw_dir.rglob("*.json"))
    assert files
    payload = json.loads(files[0].read_text())
    assert set(payload) == {"request", "fetched_at_utc", "http_status", "response"}
    fetch_rows = loaded.execute("SELECT raw_path FROM weather_fetches").fetchall()
    assert all(Path(r[0]).exists() for r in fetch_rows)


def test_wrong_units_stop_the_collector_before_writing(loaded, raw_dir):
    good = FakeOpenMeteo()
    col.discover_cells(loaded, good, raw_dir, sleep=NO_SLEEP)
    bad = FakeOpenMeteo(units_override={"wind_speed_10m": "mph"})
    with pytest.raises(om.UnitMismatch):
        col.fetch_single_run(loaded, bad, col.cells_for(loaded), datetime(2026, 10, 15, 12, tzinfo=UTC), raw_dir, sleep=NO_SLEEP)
    assert loaded.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()[0] == 0


def test_cell_drift_is_detected(loaded, raw_dir):
    api = FakeOpenMeteo()
    col.discover_cells(loaded, api, raw_dir, sleep=NO_SLEEP)
    cells = [col.Cell(c.cell_id, c.lat + 0.01, c.lon) for c in col.cells_for(loaded)]
    with pytest.raises(om.ResponseError, match="drifted"):
        col.fetch_single_run(loaded, api, cells, datetime(2026, 10, 15, 12, tzinfo=UTC), raw_dir, sleep=NO_SLEEP)
