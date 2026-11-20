"""Module 4 end to end on synthetic data: route + fake weather + synthetic DEM."""

from datetime import UTC, datetime

import pytest

from fake_openmeteo import FakeOpenMeteo
from mountain_software.exposure import index as ex
from mountain_software.terrain.pipeline import TerrainParams, route_terrain
from mountain_software.weather import collector as col
from test_terrain_pipeline import setup  # noqa: F401  (pytest fixture)

NO_SLEEP = lambda s: None  # noqa: E731


@pytest.fixture
def ready(setup, tmp_path):  # noqa: F811
    conn, dem_path = setup
    route_terrain(conn, "cone_walk", dem_path=dem_path, params=TerrainParams(wind_directions_deg=tuple(float(d) for d in range(0, 360, 10))))
    api = FakeOpenMeteo()
    col.discover_cells(conn, api, tmp_path / "raw", sleep=NO_SLEEP)
    cells = col.cells_for(conn)
    for run in ("2026-10-15T00:00", "2026-10-15T12:00", "2026-10-16T00:00", "2026-10-16T12:00"):
        col.fetch_single_run(conn, api, cells, datetime.strptime(run, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC), tmp_path / "raw", sleep=NO_SLEEP)
    return conn


def test_no_look_ahead(ready):
    conn = ready
    cell = col.cells_for(conn)[0].cell_id
    as_of = datetime(2026, 10, 16, 6, tzinfo=UTC)
    wx = ex.best_available_weather(conn, cell, datetime(2026, 10, 15, 0, tzinfo=UTC), as_of, as_of)
    assert wx and all(w.issue_time <= as_of for w in wx)
    # The 12Z run is not published until 15Z: at 14Z only older runs count.
    early = datetime(2026, 10, 15, 14, tzinfo=UTC)
    wx_early = ex.best_available_weather(conn, cell, datetime(2026, 10, 15, 0, tzinfo=UTC), early, early)
    assert max(w.issue_time for w in wx_early) == datetime(2026, 10, 15, 0, tzinfo=UTC)
    # Each hour comes from the newest run issued by as_of.
    by_hour = {w.valid_time: w.issue_time for w in wx}
    assert by_hour[datetime(2026, 10, 15, 13, tzinfo=UTC)] == datetime(2026, 10, 15, 12, tzinfo=UTC)
    assert by_hour[datetime(2026, 10, 16, 5, tzinfo=UTC)] == datetime(2026, 10, 16, 0, tzinfo=UTC)


def test_route_exposure_stores_relative_index(ready):
    conn = ready
    as_of = datetime(2026, 10, 16, 6, tzinfo=UTC)
    result = ex.route_exposure(conn, "cone_walk", as_of, ex.ExposureParams(transport_threshold_kmh=1.0), allow_stitched=False)
    assert result.data_age_hours == pytest.approx(6.0)  # 00Z run, published by 03Z, used at 06Z
    n = ex.store_exposure(conn, result)
    n_pts = conn.execute("SELECT COUNT(*) FROM route_points").fetchone()[0]
    assert n == 2 * n_pts
    rel = [r[0] for r in conn.execute("SELECT relative_index FROM exposure_scores WHERE method = 'M1'")]
    assert min(rel) == 0.0 and max(rel) == 1.0
    # Rerun for the same as_of replaces, not duplicates.
    ex.store_exposure(conn, result)
    assert conn.execute("SELECT COUNT(*) FROM exposure_scores").fetchone()[0] == n


def test_scan_writes_one_row_per_day(ready, tmp_path):
    from datetime import date

    from mountain_software.exposure.scan import scan

    rows = scan(ready, "cone_walk", date(2026, 10, 15), date(2026, 10, 16), tmp_path / "s.csv", hour_utc=12,
                params=ex.ExposureParams(transport_threshold_kmh=1.0))
    assert len(rows) == 2
    assert (tmp_path / "s.csv").read_text().count("\n") == 3
    assert rows[1]["m1_informative"] is True


def test_stitched_fallback_respects_publication_lag(ready, tmp_path):
    conn = ready
    api = FakeOpenMeteo()
    cells = col.cells_for(conn)
    from datetime import date

    col.fetch_stitched(conn, api, cells, date(2026, 10, 19), date(2026, 10, 19), tmp_path / "raw", sleep=NO_SLEEP)
    as_of = datetime(2026, 10, 19, 12, tzinfo=UTC)
    wx = ex.best_available_weather(conn, cells[0].cell_id, datetime(2026, 10, 19, 0, tzinfo=UTC), as_of, as_of)
    stitched = [w for w in wx if w.product == "historical_stitched"]
    assert stitched and max(w.valid_time for w in stitched) == datetime(2026, 10, 19, 9, tzinfo=UTC)


def test_window_has_exactly_window_hours(ready):
    conn = ready
    cell = col.cells_for(conn)[0].cell_id
    as_of = datetime(2026, 10, 16, 12, tzinfo=UTC)
    wx = ex.best_available_weather(conn, cell, datetime(2026, 10, 16, 0, tzinfo=UTC), as_of, as_of)
    assert len(wx) == 12 and wx[0].valid_time == datetime(2026, 10, 16, 1, tzinfo=UTC)


def test_snow_before_window_counts():
    t0 = datetime(2026, 10, 16, 0, tzinfo=UTC)
    from datetime import timedelta

    history = [ex.HourlyWeather(t0 - timedelta(hours=h), 0.0, 270.0, 2.0, "single_run", t0) for h in range(1, 11)]
    window = [ex.HourlyWeather(t0 + timedelta(hours=1), 50.0, 270.0, 0.0, "single_run", t0)]
    p = ex.ExposureParams()
    with_hist = ex.score_point(window, 90.0, {270.0: 10.0}, p, history)
    without = ex.score_point(window, 90.0, {270.0: 10.0}, p)
    assert with_hist.m1_loading > without.m1_loading > 0


def test_hybrid_wind_uses_700_speed_and_10m_direction(ready):
    conn = ready
    cell = col.cells_for(conn)[0].cell_id
    as_of = datetime(2026, 10, 16, 12, tzinfo=UTC)
    start = datetime(2026, 10, 16, 6, tzinfo=UTC)
    hy = ex.best_available_weather(conn, cell, start, as_of, as_of, wind_level="hybrid")
    up = ex.best_available_weather(conn, cell, start, as_of, as_of, wind_level="700hPa")
    lo = ex.best_available_weather(conn, cell, start, as_of, as_of, wind_level="10m")
    assert [w.wind_speed_kmh for w in hy] == [w.wind_speed_kmh for w in up]
    assert [w.wind_from_deg for w in hy] == [w.wind_from_deg for w in lo]
