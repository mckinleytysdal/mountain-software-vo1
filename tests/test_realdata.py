"""Checks against the real GPX files, run locally only.

The files live in git-ignored folders, so on GitHub and in a clean checkout
every test here is skipped. Tolerances: distance 1 %, GPX gain 5 %, maximum
GPX elevation 5 m, clean point count exact.
"""

import tomllib
from pathlib import Path

import pytest

from mountain_software.gpx import parse_gpx
from mountain_software.routes import process_track

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = tomllib.loads((ROOT / "data/routes/manifest.toml").read_text())
ROUTES = [r for r in MANIFEST["routes"] if r.get("expected")]


@pytest.mark.realdata
@pytest.mark.parametrize("entry", ROUTES, ids=[r["route_id"] for r in ROUTES])
def test_real_track_matches_hand_checked_values(entry):
    path = ROOT / "data/routes" / entry["file"]
    if not path.exists():
        pytest.skip(f"{path.relative_to(ROOT)} not present (git-ignored; place it locally to run)")
    p = process_track(parse_gpx(path))
    exp = entry["expected"]
    assert p.distance_m / 1000 == pytest.approx(exp["distance_km"], rel=0.01)
    if "distance_raw_km" in exp:
        assert p.distance_raw_m / 1000 == pytest.approx(exp["distance_raw_km"], rel=0.01)
    if "gain_m" in exp:
        assert p.gain_gpx_m == pytest.approx(exp["gain_m"], rel=0.05)
    if "max_ele_m" in exp:
        assert p.max_ele_gpx_m == pytest.approx(exp["max_ele_m"], abs=5)
    if "points_clean" in exp:
        assert len(p.clean) == exp["points_clean"]
    gaps = [b.distance_along_m - a.distance_along_m for a, b in zip(p.route_points, p.route_points[1:])]
    assert all(abs(g - 250) < 1e-6 for g in gaps[:-1])
