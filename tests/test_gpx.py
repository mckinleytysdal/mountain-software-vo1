from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gpx_factory import START, gpx_from_points, jittery_1hz_walk, straight_line_points
from mountain_software.geo import path_length_m
from mountain_software.gpx import (
    GpxError,
    TrackPoint,
    clean_points,
    median_interval_s,
    parse_gpx,
    parse_time_utc,
    thin_by_time,
)


def test_parse_gpx11_track_points_elevation_and_time():
    pts = straight_line_points(500, 100)
    times = [START + timedelta(seconds=i) for i in range(len(pts))]
    track = parse_gpx(gpx_from_points(pts, times))
    assert len(track.points) == 6
    assert track.points[0].ele_gpx_m == pytest.approx(2000.0)
    assert track.points[0].time_utc == START
    assert track.is_timed
    assert track.creator == "synthetic-test"
    assert track.name == "synthetic"


def test_parse_reads_copyright_licence_and_waypoints():
    meta = '<copyright author="Example Co"><license>https://example.org/terms</license></copyright>'
    wpts = '<wpt lat="51.5" lon="-116.2"><name>Hut</name></wpt>\n'
    track = parse_gpx(gpx_from_points(straight_line_points(200, 100), extra_metadata=meta, waypoints=wpts))
    assert track.copyright_author == "Example Co"
    assert track.licence == "https://example.org/terms"
    assert track.waypoints[0].name == "Hut"
    assert not track.is_timed


def test_parse_gpx10_without_namespace_prefix_and_route_points():
    text = (
        '<gpx version="1.0" xmlns="http://www.topografix.com/GPX/1/0">'
        '<rte><rtept lat="51.0" lon="-116.0"><ele>2000</ele></rtept>'
        '<rtept lat="51.001" lon="-116.0"/></rte></gpx>'
    )
    track = parse_gpx(text)
    assert [p.lat for p in track.points] == [51.0, 51.001]
    assert track.points[1].ele_gpx_m is None


def test_parse_from_path(tmp_path: Path):
    f = tmp_path / "t.gpx"
    f.write_text(gpx_from_points(straight_line_points(200, 100)))
    assert len(parse_gpx(f).points) == 3


@pytest.mark.parametrize("bad", ["not xml", "<kml></kml>", '<gpx xmlns="http://www.topografix.com/GPX/1/1"></gpx>'])
def test_bad_files_raise(bad):
    with pytest.raises(GpxError):
        parse_gpx(bad)


def test_times_are_converted_to_utc():
    assert parse_time_utc("2026-10-16T04:59:00-06:00") == datetime(2026, 10, 16, 10, 59, tzinfo=UTC)
    assert parse_time_utc("2026-10-16T10:59:00Z") == datetime(2026, 10, 16, 10, 59, tzinfo=UTC)
    # No zone given: GPX says times are UTC.
    assert parse_time_utc("2026-10-16T10:59:00").tzinfo is not None


def test_clean_drops_repeats_and_impossible_points():
    pts = [
        TrackPoint(51.0, -116.0),
        TrackPoint(51.0, -116.0),  # repeat while paused
        TrackPoint(0.0, 0.0),  # "null island" GPS glitch
        TrackPoint(95.0, -116.0),  # impossible latitude
        TrackPoint(51.001, -116.0),
    ]
    assert clean_points(pts) == [TrackPoint(51.0, -116.0), TrackPoint(51.001, -116.0)]


def test_thinning_keeps_first_last_and_spacing():
    pts = [TrackPoint(51 + i * 1e-5, -116, None, START + timedelta(seconds=i)) for i in range(95)]
    kept = thin_by_time(pts, 10)
    assert kept[0] == pts[0] and kept[-1] == pts[-1]
    gaps = [(b.time_utc - a.time_utc).total_seconds() for a, b in zip(kept, kept[1:-1])]
    assert all(g >= 10 for g in gaps)
    assert len(kept) == 11  # t = 0, 10, ..., 90, plus the last point at 94


def test_thinning_removes_gps_wobble_distance():
    """The North Victoria effect in miniature: 1 Hz wobble inflates distance.

    Synthetic 3 km walk at 0.8 m/s with 2.5 m GPS wobble. Raw 1 Hz distance is
    far too long (about 3x); after thinning to ~10 s the error shrinks to
    roughly a tenth of that. Pure random wobble is harsher than real GPS error,
    which drifts smoothly, so real tracks thin even better.
    """
    raw_pts, times, true_len = jittery_1hz_walk()
    pts = [TrackPoint(la, lo, e, t) for (la, lo, e), t in zip(raw_pts, times)]
    raw = path_length_m([(p.lat, p.lon) for p in pts])
    thinned = thin_by_time(pts, 10)
    thin = path_length_m([(p.lat, p.lon) for p in thinned])
    assert median_interval_s(pts) == 1
    assert raw > 2.5 * true_len
    assert thin == pytest.approx(true_len, rel=0.15)
    assert (thin - true_len) < (raw - true_len) / 10


def test_median_interval_untimed_is_none():
    assert median_interval_s([TrackPoint(51, -116), TrackPoint(51.1, -116)]) is None
