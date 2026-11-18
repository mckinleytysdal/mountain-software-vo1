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
