from datetime import timedelta
from pathlib import Path

import pytest

from gpx_factory import START, gpx_from_points, jittery_1hz_walk, straight_line_points
from mountain_software import db
from mountain_software.routes import load_all, load_manifest

MANIFEST = """
[[regions]]
region_id = "lake_louise"
name = "Lake Louise"

[[peaks]]
peak_id = "test_peak"
name = "Test Peak"
region_id = "lake_louise"
published_elev_m = 3000
is_11000er = false

[[routes]]
route_id = "timed"
name = "Timed synthetic walk"
region_id = "lake_louise"
peak_id = "test_peak"
route_shape = "one_way"
file = "own/timed.gpx"
source = "synthetic"
download_date = "2026-11-18"
terms_note = "made up for tests"
redistribution_allowed = true
committed_to_repo = false

[[routes]]
route_id = "untimed"
name = "Untimed synthetic line"
region_id = "lake_louise"
route_shape = "one_way"
file = "third_party/untimed.gpx"
source = "synthetic"
download_date = "2026-11-18"
terms_note = "made up for tests"
redistribution_allowed = false
committed_to_repo = false

[[routes]]
route_id = "absent"
name = "File not present"
region_id = "lake_louise"
route_shape = "loop"
file = "third_party/absent.gpx"
source = "synthetic"
download_date = "2026-11-18"
terms_note = "made up for tests"
redistribution_allowed = false
committed_to_repo = false
"""


@pytest.fixture
def routes_dir(tmp_path: Path) -> Path:
    (tmp_path / "own").mkdir()
    (tmp_path / "third_party").mkdir()
    pts, times, _ = jittery_1hz_walk(length_m=2000)
    (tmp_path / "own/timed.gpx").write_text(gpx_from_points(pts, times))
    (tmp_path / "third_party/untimed.gpx").write_text(gpx_from_points(straight_line_points(1200, 20, climb_per_m=0.25)))
    (tmp_path / "manifest.toml").write_text(MANIFEST)
    return tmp_path


def test_load_all_stores_routes_points_and_sources(conn, routes_dir):
    result = load_all(conn, routes_dir / "manifest.toml")
    assert set(result.loaded) == {"timed", "untimed"}
    assert set(result.missing) == {"absent"}

    routes = {r["route_id"]: r for r in conn.execute("SELECT * FROM routes")}
    assert routes["timed"]["is_timed"] == 1 and routes["timed"]["thin_interval_s"] == 10
    assert routes["timed"]["track_date_local"] == START.date().isoformat()
    assert routes["untimed"]["thin_interval_s"] is None
    assert routes["untimed"]["distance_m"] == pytest.approx(1200, abs=1)
    assert routes["untimed"]["gain_gpx_m"] == pytest.approx(300, abs=1)
    assert routes["timed"]["distance_raw_m"] > routes["timed"]["distance_m"]

    # Every loaded track has exactly one route_sources row.
    srcs = conn.execute("SELECT route_id, download_date, terms_note, file_sha256 FROM route_sources").fetchall()
    assert {s["route_id"] for s in srcs} == {"timed", "untimed"}
    assert all(len(s["file_sha256"]) == 64 for s in srcs)

    n_untimed = conn.execute("SELECT COUNT(*) FROM route_points WHERE route_id = 'untimed'").fetchone()[0]
    assert n_untimed == 6  # 0, 250, 500, 750, 1000, 1200


def test_route_points_about_250_m_apart(conn, routes_dir):
    load_all(conn, routes_dir / "manifest.toml")
    d = [r[0] for r in conn.execute("SELECT distance_along_m FROM route_points WHERE route_id='timed' ORDER BY seq")]
    gaps = [b - a for a, b in zip(d, d[1:])]
    assert all(g == pytest.approx(250) for g in gaps[:-1])
    assert 0 < gaps[-1] <= 250


def test_rerun_makes_no_duplicates(conn, routes_dir):
    load_all(conn, routes_dir / "manifest.toml")
    counts1 = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("routes", "route_points", "route_sources", "regions", "peaks")]
    load_all(conn, routes_dir / "manifest.toml")
    counts2 = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("routes", "route_points", "route_sources", "regions", "peaks")]
    assert counts1 == counts2


def test_route_needs_known_region(conn):
    with pytest.raises(Exception):
        with conn:
            conn.execute(
                "INSERT INTO routes (route_id, name, region_id, route_shape, is_timed, n_points_raw, n_points_clean,"
                " n_points_used, distance_raw_m, distance_m, gain_threshold_m, method_version, loaded_at_utc)"
                " VALUES ('x', 'x', 'nowhere', 'loop', 0, 2, 2, 2, 1, 1, 3, 'v', 'now')"
            )


def test_manifest_rejects_missing_terms(tmp_path):
    bad = MANIFEST.replace('terms_note = "made up for tests"', 'terms_note = ""', 1)
    (tmp_path / "m.toml").write_text(bad)
    with pytest.raises(ValueError, match="terms_note"):
        load_manifest(tmp_path / "m.toml")


def test_manifest_rejects_unknown_region(tmp_path):
    bad = MANIFEST.replace('region_id = "lake_louise"\nroute_shape = "loop"', 'region_id = "mars"\nroute_shape = "loop"')
    (tmp_path / "m.toml").write_text(bad)
    with pytest.raises(ValueError, match="unknown region"):
        load_manifest(tmp_path / "m.toml")


def test_schema_migration_is_idempotent(tmp_path):
    path = tmp_path / "x.sqlite"
    c1 = db.connect(path)
    v1 = c1.execute("PRAGMA user_version").fetchone()[0]
    c1.close()
    c2 = db.connect(path)
    assert c2.execute("PRAGMA user_version").fetchone()[0] == v1 == len(db.MIGRATIONS)
    assert {"regions", "peaks", "routes", "route_points", "route_sources"} <= db.table_names(c2)


def test_unchanged_reload_keeps_downstream_rows(conn, routes_dir):
    load_all(conn, routes_dir / "manifest.toml")
    # Pretend later modules attached something to a route point.
    conn.execute("INSERT INTO weather_cells (model, grid_lat, grid_lon, first_seen_utc) VALUES ('m', 1, 1, 'x')")
    conn.execute(
        "INSERT INTO route_point_cells (route_id, seq, model, cell_id, distance_to_cell_m, method_version)"
        " VALUES ('untimed', 0, 'm', 1, 0, 'v')"
    )
    conn.commit()
    result = load_all(conn, routes_dir / "manifest.toml")
    assert set(result.unchanged) == {"timed", "untimed"} and not result.loaded
    assert conn.execute("SELECT COUNT(*) FROM route_point_cells").fetchone()[0] == 1
    forced = load_all(conn, routes_dir / "manifest.toml", force=True)
    assert set(forced.loaded) == {"timed", "untimed"}
    assert conn.execute("SELECT COUNT(*) FROM route_point_cells").fetchone()[0] == 0


def test_migration_comments_match_their_position():
    import inspect
    import re

    src = inspect.getsource(db)
    numbers = [int(n) for n in re.findall(r"^    # (\d+):", src, flags=re.M)]
    assert numbers == list(range(1, len(db.MIGRATIONS) + 1))


def test_failed_migration_leaves_version_unchanged(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "x.sqlite"
    db.connect(path).close()
    good = len(db.MIGRATIONS)
    monkeypatch.setattr(db, "MIGRATIONS", db.MIGRATIONS + ["CREATE TABLE extra (a INT); CREATE TABLE regions (b INT);"])
    with pytest.raises(sqlite3.OperationalError):
        db.connect(path)
    c = sqlite3.connect(path)
    assert c.execute("PRAGMA user_version").fetchone()[0] == good
    assert "extra" not in {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
