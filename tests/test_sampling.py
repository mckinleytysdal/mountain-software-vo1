import pytest

from gpx_factory import straight_line_points
from mountain_software.geo import haversine_m
from mountain_software.gpx import TrackPoint
from mountain_software.sampling import resample


def _track(length_m, step_m, climb=0.0):
    return [TrackPoint(la, lo, e) for la, lo, e in straight_line_points(length_m, step_m, climb_per_m=climb)]


def test_points_every_250_m_on_straight_line():
    rps = resample(_track(1000, 37), 250)  # odd source spacing on purpose
    assert [round(r.distance_along_m) for r in rps][:4] == [0, 250, 500, 750]
    for a, b in zip(rps, rps[1:]):
        assert haversine_m(a.lat, a.lon, b.lat, b.lon) == pytest.approx(b.distance_along_m - a.distance_along_m, abs=0.5)


def test_last_point_is_track_end_and_gap_is_shorter():
    trk = _track(1100, 50)
    rps = resample(trk, 250)
    assert rps[-1].lat == pytest.approx(trk[-1].lat)
    gaps = [b.distance_along_m - a.distance_along_m for a, b in zip(rps, rps[1:])]
    assert all(g == pytest.approx(250) for g in gaps[:-1])
    assert gaps[-1] == pytest.approx(100, abs=1)


def test_elevation_is_interpolated():
    rps = resample(_track(1000, 100, climb=0.2), 250)
    assert rps[1].ele_gpx_m == pytest.approx(2050, abs=0.5)


def test_spacing_follows_bends_not_crow_flight():
    # Out 500 m north, then back 500 m south: 1000 m walked, start == end.
    out = straight_line_points(500, 50)
    pts = [TrackPoint(*p) for p in out + out[-2::-1]]
    rps = resample(pts, 250)
    assert rps[-1].distance_along_m == pytest.approx(1000, abs=1)
    assert len(rps) == 5


def test_short_track_and_bad_spacing():
    assert len(resample(_track(100, 50), 250)) == 2
    assert resample([], 250) == []
    with pytest.raises(ValueError):
        resample(_track(100, 50), 0)
