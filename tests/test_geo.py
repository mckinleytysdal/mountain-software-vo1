import math

import pytest

from mountain_software.geo import (
    angular_difference_deg,
    elevation_gain_m,
    haversine_m,
    initial_bearing_deg,
    path_length_m,
)


def test_one_degree_of_latitude_is_about_111_km():
    assert haversine_m(51.0, -116.0, 52.0, -116.0) == pytest.approx(111_195, rel=1e-3)


def test_zero_distance_for_same_point():
    assert haversine_m(51.4, -116.3, 51.4, -116.3) == 0.0


def test_path_length_adds_legs():
    legs = [(51.0, -116.0), (51.001, -116.0), (51.002, -116.0)]
    assert path_length_m(legs) == pytest.approx(2 * haversine_m(51.0, -116.0, 51.001, -116.0))
    assert path_length_m(legs[:1]) == 0.0


def test_gain_ignores_wobble_below_threshold():
    # Standing still with +-2 m noise: no real climbing.
    assert elevation_gain_m([2000, 2002, 2000, 2002, 2000, 2001], threshold_m=3) == 0


def test_gain_counts_real_climb_and_skips_none():
    assert elevation_gain_m([2000, None, 2005, 2010, 2004, 2020], threshold_m=3) == pytest.approx(26)


def test_wind_direction_is_circular():
    assert angular_difference_deg(359, 1) == 2
    assert angular_difference_deg(10, 190) == 180
    assert angular_difference_deg(90, 90) == 0


def test_bearing_due_east_and_north():
    assert initial_bearing_deg(51, -116, 52, -116) == pytest.approx(0, abs=1e-6)
    assert initial_bearing_deg(0, 0, 0, 1) == pytest.approx(90, abs=1e-6)
    assert math.isfinite(initial_bearing_deg(51, -116, 51, -116))
