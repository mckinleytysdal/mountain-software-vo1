"""Module 3 pipeline on a synthetic DEM GeoTIFF (no network)."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform

from gpx_factory import gpx_from_points, straight_line_points
from mountain_software.routes import load_all
from mountain_software.terrain import dem as demmod
from mountain_software.terrain import features as tf
from mountain_software.terrain.pipeline import TerrainParams, bbox_with_buffer, route_terrain

CRS = "EPSG:3979"
MANIFEST = """
[[regions]]
region_id = "lake_louise"
name = "Lake Louise"

[[routes]]
route_id = "cone_walk"
name = "Walk up a synthetic cone"
region_id = "lake_louise"
route_shape = "one_way"
file = "own/cone.gpx"
source = "synthetic"
download_date = "2026-11-18"
terms_note = "test"
"""

LAT0, LON0 = 51.40, -116.30


def write_cone_dem(path: Path, n: int = 201, res: float = 30.0) -> tuple[float, float]:
    """A 600 m cone centred on (LAT0 + 0.0135, LON0); returns the centre in EPSG:3979."""
    (cx,), (cy,) = transform("EPSG:4326", CRS, [LON0], [LAT0 + 0.0135])
    half = n // 2
    rows, cols = np.mgrid[0:n, 0:n]
    r = np.hypot(rows - half, cols - half) * res
    z = (2600 - 0.4 * r).astype("float32")
    t = from_origin(cx - (half + 0.5) * res, cy + (half + 0.5) * res, res, res)
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n, count=1, dtype="float32", crs=CRS, transform=t, nodata=-32767) as dst:
        dst.write(z, 1)
    return cx, cy


@pytest.fixture
def setup(conn, tmp_path):
    (tmp_path / "own").mkdir()
    # 3 km due north from LAT0: climbs the south flank, crosses the top near 1.5 km.
    (tmp_path / "own/cone.gpx").write_text(gpx_from_points(straight_line_points(3000, 30, lat0=LAT0, lon0=LON0)))
    (tmp_path / "manifest.toml").write_text(MANIFEST)
    load_all(conn, tmp_path / "manifest.toml")
    dem_path = tmp_path / "cone.tif"
    write_cone_dem(dem_path)
    return conn, dem_path


def test_route_terrain_stores_features_and_sx(setup):
    conn, dem_path = setup
    params = TerrainParams(sx_dmax_m=(300.0,), wind_directions_deg=(0.0, 90.0, 180.0, 270.0))
    summary = route_terrain(conn, "cone_walk", dem_path=dem_path, params=params)
    assert summary["points_outside_dem"] == 0
    n_pts = conn.execute("SELECT COUNT(*) FROM route_points").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM terrain_features").fetchone()[0] == n_pts
    assert conn.execute("SELECT COUNT(*) FROM route_point_sx").fetchone()[0] == n_pts * 4

    rows = {r["seq"]: r for r in conn.execute("SELECT * FROM terrain_features")}
    top = max(rows.values(), key=lambda r: r["dem_elev_m"])
    assert top["dem_elev_m"] > 2550
    assert top["landform_class"] == "ridge"
    # Lower south flank faces about south (true north), cone slope ~21.8°.
    south = rows[1]
    assert south["slope_deg"] == pytest.approx(21.8, abs=0.5)
    assert tf.angular_difference(south["aspect_true_deg"], 180.0) < 3
    assert south["surface_class"] == "unknown"


def test_rerun_replaces_rows(setup):
    conn, dem_path = setup
    params = TerrainParams(sx_dmax_m=(100.0,), wind_directions_deg=(0.0,))
    route_terrain(conn, "cone_walk", dem_path=dem_path, params=params)
    route_terrain(conn, "cone_walk", dem_path=dem_path, params=params)
    n_pts = conn.execute("SELECT COUNT(*) FROM route_points").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM terrain_features").fetchone()[0] == n_pts
    assert conn.execute("SELECT COUNT(*) FROM dem_sources").fetchone()[0] == 1


def test_sx_on_south_flank_with_north_wind_is_sheltered(setup):
    conn, dem_path = setup
    params = TerrainParams(sx_dmax_m=(300.0,), wind_directions_deg=(0.0, 180.0))
    route_terrain(conn, "cone_walk", dem_path=dem_path, params=params)
    sx = dict(
        ((r["wind_from_true_deg"]), r["sx_deg"])
        for r in conn.execute("SELECT wind_from_true_deg, sx_deg FROM route_point_sx WHERE seq = 2")
    )
    assert sx[0.0] > 0  # wind from the north: the cone is upwind, point is in its lee
    assert sx[180.0] < 0  # wind from the south: point faces it, exposed


def test_convergence_is_large_in_the_rockies():
    conv = demmod.convergence_deg([-116.3], [51.4], CRS)[0]
    # EPSG:3979 central meridian is -95°, so grid north is far from true north.
    assert abs(conv) > 10


def test_bbox_with_buffer():
    w, s, e, n = bbox_with_buffer([51.0, 51.1], [-116.2, -116.1], 1000)
    assert s == pytest.approx(51.0 - 0.009, abs=1e-3) and e > -116.1


def test_dem_cache_covers_check(tmp_path):
    p = tmp_path / "c.tif"
    write_cone_dem(p)
    with rasterio.open(p, "r+") as dst:
        dst.update_tags(request_bounds_wgs84="[-116.4, 51.3, -116.2, 51.5]")
    assert demmod.cached_covers(p, -116.35, 51.35, -116.25, 51.45)
    assert not demmod.cached_covers(p, -116.5, 51.35, -116.25, 51.45)
