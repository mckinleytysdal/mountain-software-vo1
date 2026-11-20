"""Terrain maths on invented surfaces whose answers are known by hand."""

import math

import numpy as np
import pytest

from mountain_software.terrain import features as tf

RES = 30.0


def plane(dz_east_per_m=0.0, dz_north_per_m=0.0, n=21):
    rows, cols = np.mgrid[0:n, 0:n]
    north_m = (n - 1 - rows) * RES  # row 0 is the north edge
    east_m = cols * RES
    return 2000 + dz_east_per_m * east_m + dz_north_per_m * north_m


def cone(n=41, height=300.0, peak=True):
    rows, cols = np.mgrid[0:n, 0:n]
    r = np.hypot(rows - n // 2, cols - n // 2) * RES
    return 2000 + (height - r * 0.5 if peak else r * 0.5)


@pytest.mark.parametrize(
    "east,north,slope,aspect",
    [
        (0.0, 1.0, 45.0, 180.0),  # rises to the north -> faces south
        (0.0, -1.0, 45.0, 0.0),  # rises to the south -> faces north
        (1.0, 0.0, 45.0, 270.0),  # rises to the east -> faces west
        (-0.5774, 0.0, 30.0, 90.0),  # tan(30°) = 0.5774, faces east
    ],
)
def test_slope_and_aspect_of_planes(east, north, slope, aspect):
    s, a = tf.slope_aspect_horn(plane(east, north), RES)
    assert s[10, 10] == pytest.approx(slope, abs=0.05)
    assert a[10, 10] == pytest.approx(aspect, abs=0.05)


def test_flat_ground_has_no_aspect():
    s, a = tf.slope_aspect_horn(plane(), RES)
    assert s[5, 5] == 0 and np.isnan(a[5, 5])


def test_curvature_sign_peak_and_bowl():
    assert tf.laplacian_curvature(cone(peak=True), RES)[20, 20] > 0
    assert tf.laplacian_curvature(cone(peak=False), RES)[20, 20] < 0
    assert tf.laplacian_curvature(plane(0.3, 0.2), RES)[10, 10] == pytest.approx(0, abs=1e-12)


def test_tpi_peak_positive_bowl_negative_plane_zero():
    assert tf.tpi(cone(peak=True), 150, RES)[20, 20] > 0
    assert tf.tpi(cone(peak=False), 150, RES)[20, 20] < 0
    assert tf.tpi(plane(0.3, 0.1), 150, RES)[10, 10] == pytest.approx(0, abs=1e-9)


def test_tpi_ignores_nan():
    z = cone()
    z[0:5, :] = np.nan
    t = tf.tpi(z, 150, RES)
    assert np.isfinite(t[20, 20]) and np.isnan(t[0, 0])


def test_slope_position_classes():
    t = np.array([1.5, 0.7, 0.0, 0.0, -0.7, -1.5])
    s = np.array([30, 30, 30, 2, 30, 30])
    assert list(tf.slope_position(t, s)) == ["ridge", "upper_slope", "middle_slope", "flat", "lower_slope", "valley"]


def test_sx_sheltered_behind_wall_and_exposed_on_top():
    z = np.full((41, 41), 2000.0)
    z[:, 25] = 2060.0  # a 60 m wall running north-south, east of the centre (col 20)
    # Wind from the east: the wall (150 m upwind) shelters the centre.
    assert tf.sx_ray(z, 20, 20, RES, 90.0, 300.0) == pytest.approx(math.degrees(math.atan2(60, 150)), abs=0.01)
    # Wind from the west: nothing upwind is higher.
    assert tf.sx_ray(z, 20, 20, RES, 270.0, 300.0) == pytest.approx(0.0, abs=1e-9)
    # On top of a peak every direction is exposed (negative).
    assert tf.sx(cone(), 20, 20, RES, 0.0, 300.0) < -10


def test_sx_respects_dmax():
    z = np.full((41, 41), 2000.0)
    z[:, 35] = 2100.0  # 450 m east of the centre
    assert tf.sx_ray(z, 20, 20, RES, 90.0, 300.0) == pytest.approx(0.0, abs=1e-9)
    assert tf.sx_ray(z, 20, 20, RES, 90.0, 600.0) > 0


def test_grid_to_true_north():
    # If true north is 15° clockwise of grid north, a slope facing grid-east
    # (90°) faces 75° true.
    assert tf.grid_to_true_deg(90.0, 15.0) == pytest.approx(75.0)
    assert tf.grid_to_true_deg(5.0, 15.0) == pytest.approx(350.0)
    assert tf.convergence_from_points(0, 0, 1, 1) == pytest.approx(45.0)


def test_bilinear():
    z = np.array([[0.0, 10.0], [20.0, 30.0]])
    assert tf.bilinear(z, 0.5, 0.5) == pytest.approx(15.0)
    assert math.isnan(tf.bilinear(z, -0.1, 0))
