"""Module 4 maths on hand-made inputs."""

from datetime import UTC, datetime, timedelta

import pytest

from mountain_software.exposure import index as ex

T0 = datetime(2026, 10, 16, 0, tzinfo=UTC)
P = ex.ExposureParams()


def hours(n, speed, wind_from, snow=0.0, product="single_run"):
    return [ex.HourlyWeather(T0 + timedelta(hours=i), speed, wind_from, snow, product, T0 if product == "single_run" else None) for i in range(n)]


def test_b0_leeward_is_downwind_and_circular():
    assert ex.b0_leeward(90, 270, 45) is True  # west wind, east-facing slope
    assert ex.b0_leeward(270, 270, 45) is False  # facing into the wind
    assert ex.b0_leeward(10, 170, 45) is True  # downwind 350, aspect 10: 20° apart across north
    assert ex.b0_leeward(None, 270, 45) is None
    assert ex.b0_leeward(90, None, 45) is None


def test_transport_zero_below_threshold_and_grows_fast():
    assert ex.transport_potential(20, 25, 4) == 0
    assert ex.transport_potential(None, 25, 4) == 0
    assert ex.transport_potential(25, 25, 4) == 0
    assert ex.transport_potential(50, 25, 4) == pytest.approx(15.0)  # 2^4 - 1
    assert ex.transport_potential(75, 25, 4) == pytest.approx(80.0)  # 3^4 - 1


def test_snow_supply_bounds():
    assert ex.snow_supply(0, 20, 0.2) == pytest.approx(0.2)
    assert ex.snow_supply(10, 20, 0.2) == pytest.approx(0.6)
    assert ex.snow_supply(100, 20, 0.2) == pytest.approx(1.0)


def test_sx_interpolation_across_north():
    sx = {0.0: 10.0, 10.0: 20.0, 350.0: -10.0}
    assert ex.sx_for_direction(sx, 5.0) == pytest.approx(15.0)
    assert ex.sx_for_direction(sx, 355.0) == pytest.approx(0.0)
    assert ex.sx_for_direction({}, 5.0) is None


def test_m1_sheltered_point_loads_exposed_point_scours():
    wx = hours(24, 50, 270, snow=1.0)
    sheltered = ex.score_point(wx, 90, {270.0: 15.0, 260.0: 15.0, 280.0: 15.0}, P)
    assert P.sx_dmax_m == 300.0
    exposed = ex.score_point(wx, 270, {270.0: -15.0, 260.0: -15.0, 280.0: -15.0}, P)
    assert sheltered.m1_loading > 0 and sheltered.m1_scour == 0
    assert exposed.m1_scour > 0 and exposed.m1_loading == 0
    assert sheltered.b0_leeward_fraction == 1.0 and exposed.b0_leeward_fraction == 0.0


def test_m1_zero_when_calm_even_if_sheltered():
    r = ex.score_point(hours(24, 10, 270, snow=2.0), 90, {270.0: 20.0}, P)
    assert r.m1_net == 0 and r.hours_used == 24


def test_m1_counts_stitched_hours():
    r = ex.score_point(hours(5, 40, 270, product="historical_stitched"), 90, {270.0: 5.0}, P)
    assert r.hours_stitched == 5


def test_relative_rank():
    assert ex.relative_rank([3.0, 1.0, 2.0]) == [1.0, 0.0, 0.5]
    assert ex.relative_rank([1.0, 1.0]) == [None, None]  # nothing to rank
    assert ex.relative_rank([1.0, 1.0, 2.0]) == [0.25, 0.25, 1.0]
    assert ex.relative_rank([None, 2.0]) == [None, 0.5]
    assert ex.relative_rank([None]) == [None]
