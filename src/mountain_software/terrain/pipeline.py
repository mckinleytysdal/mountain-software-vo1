"""Module 3 pipeline: DEM window -> terrain grids -> values at each route point.

Steps for one route:
1. take the route points' bounding box, add a buffer, read that DEM window;
2. compute grids: slope, aspect, curvature, small and large TPI, classes;
3. for each route point, read the grid values at its position;
4. compute Sx for 36 wind directions (every 10°) and each search distance;
5. store everything with the DEM's fingerprint and the parameters used.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import dem as demmod
from . import features as tf

METHOD_VERSION = f"{tf.METHOD_VERSION}+route-sample-v1"


@dataclass(frozen=True)
class TerrainParams:
    buffer_m: float = 2000.0
    tpi_small_m: float = 150.0
    tpi_large_m: float = 1000.0
    steep_deg: float = 30.0
    basin_max_slope_deg: float = 25.0
    flat_slope_deg: float = 5.0
    sx_dmax_m: tuple[float, ...] = (100.0, 300.0)
    sx_window_deg: float = 30.0
    sx_increment_deg: float = 5.0
    wind_directions_deg: tuple[float, ...] = field(default_factory=lambda: tuple(float(d) for d in range(0, 360, 10)))


@dataclass
class TerrainGrids:
    grid: demmod.DemGrid
    slope: np.ndarray
    aspect_grid: np.ndarray
    curvature: np.ndarray
    tpi_small: np.ndarray
    tpi_large: np.ndarray
    tpi_small_std: np.ndarray
    tpi_large_std: np.ndarray
    slope_position: np.ndarray
    landform: np.ndarray


def compute_grids(grid: demmod.DemGrid, p: TerrainParams) -> TerrainGrids:
    z, res = grid.z, grid.res_m
    slope, aspect = tf.slope_aspect_horn(z, res)
    ts = tf.tpi(z, p.tpi_small_m, res)
    tl = tf.tpi(z, p.tpi_large_m, res)
    ts_std, tl_std = tf.standardise(ts), tf.standardise(tl)
    return TerrainGrids(
        grid=grid,
        slope=slope,
        aspect_grid=aspect,
        curvature=tf.laplacian_curvature(z, res),
        tpi_small=ts,
        tpi_large=tl,
        tpi_small_std=ts_std,
        tpi_large_std=tl_std,
        slope_position=tf.slope_position(tl_std, slope, p.flat_slope_deg),
        landform=tf.landform_class(slope, ts_std, tl_std, p.steep_deg, p.basin_max_slope_deg),
    )


def bbox_with_buffer(lats: list[float], lons: list[float], buffer_m: float) -> tuple[float, float, float, float]:
    """(west, south, east, north) in degrees, grown by ``buffer_m`` on every side."""
    mid = math.radians((min(lats) + max(lats)) / 2)
    dlat = buffer_m / 111_195.0
    dlon = buffer_m / (111_195.0 * math.cos(mid))
    return min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat


def _nearest(arr: np.ndarray, row: float, col: float):
    r, c = int(round(row)), int(round(col))
    if 0 <= r < arr.shape[0] and 0 <= c < arr.shape[1]:
        return arr[r, c]
    return None


def _num(x) -> float | None:
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def upsert_dem_source(conn: sqlite3.Connection, grid: demmod.DemGrid) -> int:
    m = grid.meta
    row = conn.execute("SELECT dem_id FROM dem_sources WHERE sha256 = ?", (m["sha256"],)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        """INSERT INTO dem_sources (name, url, licence, crs, res_m, path, sha256, fetched_at_utc, request_bounds_wgs84)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (m["dem_name"], m["url"], m["licence"], grid.crs, grid.res_m, m["path"], m["sha256"], m.get("fetched_at_utc"), m.get("request_bounds_wgs84")),
    )
    return int(cur.lastrowid)


def route_terrain(
    conn: sqlite3.Connection,
    route_id: str,
    dem_path: Path | None = None,
    dem_dir: Path = demmod.DEFAULT_DEM_DIR,
    params: TerrainParams | None = None,
) -> dict:
    """Compute and store terrain features and Sx for every point of one route.

    ``dem_path`` lets tests (or a manual download) supply the DEM file; by
    default the window is read from MRDEM-30 and cached in ``dem_dir``.
    Returns a small summary dict.
    """
    p = params or TerrainParams()
    pts = conn.execute(
        "SELECT seq, lat, lon FROM route_points WHERE route_id = ? ORDER BY seq", (route_id,)
    ).fetchall()
    if not pts:
        raise ValueError(f"route {route_id} has no route points; load routes first")
    lats = [r["lat"] for r in pts]
    lons = [r["lon"] for r in pts]
    if dem_path is None:
        dem_path = demmod.fetch_window(*bbox_with_buffer(lats, lons, p.buffer_m), name=f"{route_id}_mrdem30", dem_dir=dem_dir)
    grid = demmod.read_grid(dem_path)
    g = compute_grids(grid, p)
    xs, ys = demmod.project_points(lons, lats, grid.crs)
    conv = demmod.convergence_deg(lons, lats, grid.crs)
    params_json = json.dumps(asdict(p), sort_keys=True)

    with conn:
        dem_id = upsert_dem_source(conn, grid)
        conn.execute("DELETE FROM terrain_features WHERE route_id = ? AND dem_id = ?", (route_id, dem_id))
        conn.execute("DELETE FROM route_point_sx WHERE route_id = ? AND dem_id = ?", (route_id, dem_id))
        n_outside = 0
        for r, x, y, cv in zip(pts, xs, ys, conv):
            row, col = grid.rowcol(x, y)
            elev = tf.bilinear(grid.z, row, col)
            if not math.isfinite(elev):
                n_outside += 1
            aspect_g = _num(_nearest(g.aspect_grid, row, col))
            conn.execute(
                """INSERT INTO terrain_features (route_id, seq, dem_id, dem_elev_m, slope_deg, aspect_true_deg,
                    convergence_deg, curvature_per_m, tpi_small_m, tpi_large_m, tpi_small_std, tpi_large_std,
                    slope_position, landform_class, surface_class, params_json, method_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', ?, ?)""",
                (
                    route_id,
                    r["seq"],
                    dem_id,
                    _num(elev),
                    _num(tf.bilinear(g.slope, row, col)),
                    None if aspect_g is None else float(tf.grid_to_true_deg(aspect_g, cv)),
                    cv,
                    _num(tf.bilinear(g.curvature, row, col)),
                    _num(tf.bilinear(g.tpi_small, row, col)),
                    _num(tf.bilinear(g.tpi_large, row, col)),
                    _num(tf.bilinear(g.tpi_small_std, row, col)),
                    _num(tf.bilinear(g.tpi_large_std, row, col)),
                    _nearest(g.slope_position, row, col) or None,
                    _nearest(g.landform, row, col) or None,
                    params_json,
                    METHOD_VERSION,
                ),
            )
            rows = []
            for dmax in p.sx_dmax_m:
                for wind_true in p.wind_directions_deg:
                    wind_grid = (wind_true + cv) % 360.0
                    val = tf.sx(grid.z, row, col, grid.res_m, wind_grid, dmax, p.sx_window_deg, p.sx_increment_deg)
                    rows.append((route_id, r["seq"], dem_id, dmax, wind_true, _num(val), METHOD_VERSION))
            conn.executemany(
                """INSERT INTO route_point_sx (route_id, seq, dem_id, dmax_m, wind_from_true_deg, sx_deg, method_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
    return {
        "route_id": route_id,
        "dem_id": dem_id,
        "points": len(pts),
        "points_outside_dem": n_outside,
        "dem_shape": grid.z.shape,
        "convergence_deg_mean": float(np.mean(conv)),
    }
