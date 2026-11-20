"""Station comparison logic with made-up station and model values (offline)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from fake_openmeteo import FakeOpenMeteo
from mountain_software.validation import stations as st
from mountain_software.weather import collector as col

META = {"stationId": 111, "name": "Test Ridge", "latitude": 51.47, "longitude": -116.35, "elevation": 2745,
        "source": "test", "externalId": "X"}


def fake_measurements(url, params=None):
    t0 = datetime.fromisoformat(params["fromDate"].replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(params["toDate"].replace("Z", "+00:00"))
    out, t = [], t0
    while t <= t1:
        out.append({"stationId": 111, "measurementDateTime": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "airTempAvg": -5.0, "windSpeedAvg": 30.0, "windDirAvg": 250, "windSpeedGust": 45.0,
                    "relativeHumidity": 80})
        t += timedelta(hours=1)
    return out


def test_fetch_chunks_and_upserts(conn, tmp_path):
    st.store_station(conn, META)
    n = st.fetch_measurements(conn, 111, date(2026, 9, 1), date(2026, 10, 15), tmp_path, fake_measurements, lambda s: None)
    assert n == 45 * 24
    assert len(list((tmp_path / "avcan/111").glob("*.json"))) == 2  # 31 + 14 days
    st.fetch_measurements(conn, 111, date(2026, 9, 1), date(2026, 9, 2), tmp_path, fake_measurements, lambda s: None)
    assert conn.execute("SELECT COUNT(*) FROM station_obs").fetchone()[0] == 45 * 24


def test_compare_pairs_hours_and_reports_bias(conn, tmp_path):
    st.store_station(conn, META)
    st.fetch_measurements(conn, 111, date(2026, 10, 15), date(2026, 10, 15), tmp_path, fake_measurements, lambda s: None)
    api = FakeOpenMeteo()
    cell = st.station_cell(conn, 111, api, tmp_path)
    assert st.station_cell(conn, 111, api, tmp_path) == cell  # remembered, no second lookup
    col.fetch_stitched(conn, api, [cell], date(2026, 10, 15), date(2026, 10, 15), tmp_path, sleep=lambda s: None)
    res = {(c.variable, c.model_variable): c for c in st.compare(
        conn, 111, datetime(2026, 10, 15, tzinfo=UTC), datetime(2026, 10, 15, 23, tzinfo=UTC))}
    c = res[("wind_speed_kmh", "wind_speed_10m_kmh")]
    assert c.n == 24 and c.station_mean == pytest.approx(30.0)
    assert c.bias == pytest.approx(c.model_mean - 30.0)
    assert res[("wind_from_deg", "wind_direction_700hpa_deg")].n == 24


def test_measurement_time_is_utc():
    assert st.parse_measurement_time("2026-11-08T03:00:00Z") == datetime(2026, 11, 8, 3, tzinfo=UTC)
