"""Draw one peak's terrain classification map (PNG) and save the class grid (GeoTIFF).

Colours are categorical (purple, blues, teal, brown, grey). They are chosen so
they do NOT look like the 5-level avalanche danger scale (green, yellow,
orange, red, black). The map shows landforms, not hazard.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from . import dem as demmod
from . import features as tf
from .pipeline import TerrainParams, compute_grids

CLASS_COLOURS = {
    "ridge": "#6a3d9a",
    "couloir_gully": "#1f4e9c",
    "basin_valley": "#5fb3c7",
    "steep_face": "#8c6d4f",
    "open_slope": "#d4d4d4",
}


def hillshade(z: np.ndarray, res_m: float, azimuth_deg: float = 315.0, altitude_deg: float = 45.0) -> np.ndarray:
    slope, aspect = tf.slope_aspect_horn(z, res_m)
    s = np.radians(slope)
    a = np.radians(np.nan_to_num(aspect))
    az = np.radians(azimuth_deg)
    alt = np.radians(altitude_deg)
    return np.clip(np.sin(alt) * np.cos(s) + np.cos(alt) * np.sin(s) * np.cos(az - a), 0, 1)


def classification_map(
    conn: sqlite3.Connection,
    route_id: str,
    dem_path: Path,
    out_png: Path,
    out_tif: Path | None = None,
    params: TerrainParams | None = None,
    title: str | None = None,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    p = params or TerrainParams()
    grid = demmod.read_grid(dem_path)
    g = compute_grids(grid, p)
    names = list(CLASS_COLOURS)
    idx = np.full(grid.z.shape, np.nan)
    for i, n in enumerate(names):
        idx[g.landform == n] = i

    a, _, c, _, e, f = grid.transform
    h, w = grid.z.shape
    extent = (c, c + a * w, f + e * h, f)

    pts = conn.execute("SELECT lat, lon FROM route_points WHERE route_id = ? ORDER BY seq", (route_id,)).fetchall()
    xs, ys = demmod.project_points([r["lon"] for r in pts], [r["lat"] for r in pts], grid.crs)
    conv = demmod.convergence_deg([r["lon"] for r in pts][:1], [r["lat"] for r in pts][:1], grid.crs)[0]

    fig, ax = plt.subplots(figsize=(9, 8), dpi=150)
    ax.imshow(hillshade(grid.z, grid.res_m), cmap="gray", extent=extent, vmin=0, vmax=1)
    ax.imshow(idx, cmap=ListedColormap(list(CLASS_COLOURS.values())), extent=extent, alpha=0.55, vmin=-0.5, vmax=len(names) - 0.5, interpolation="nearest")
    ax.plot(xs, ys, color="white", lw=3.2)
    ax.plot(xs, ys, color="black", lw=1.4, label="route (route points every 250 m)")
    ax.set_xticks([])
    ax.set_yticks([])
    # True-north arrow: grid north is "up"; true north is rotated by the convergence.
    import math

    ax.annotate(
        "true N",
        xy=(0.93 + 0.05 * math.sin(math.radians(conv)), 0.88 + 0.05 * math.cos(math.radians(conv))),
        xytext=(0.93, 0.88),
        xycoords="axes fraction",
        arrowprops={"arrowstyle": "->", "lw": 1.5},
        ha="center",
        va="top",
        fontsize=8,
    )
    handles = [Patch(color=col, label=n.replace("_", " ")) for n, col in CLASS_COLOURS.items()]
    ax.legend(handles=handles + [ax.lines[-1]], loc="lower left", fontsize=8, framealpha=0.9)
    ax.set_title(title or f"{route_id}: rule-based landform classes from {grid.meta['dem_name']}", fontsize=10)
    fig.text(
        0.01,
        0.04,
        "Landform classes from a 30 m DEM (method {method}). Exploratory; not a hazard map. "
        "Glacier, rock and snow surface are not classified. DEM: NRCan MRDEM-30, OGL-Canada 2.0. "
        "Official avalanche forecasts: avalanche.ca/forecasts".format(method=tf.METHOD_VERSION),
        fontsize=6.5,
        wrap=True,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)

    if out_tif is not None:
        import rasterio
        from rasterio.transform import Affine

        with rasterio.open(
            out_tif, "w", driver="GTiff", height=h, width=w, count=1, dtype="int16", crs=grid.crs,
            transform=Affine(*grid.transform), nodata=-1, compress="deflate",
        ) as dst:
            dst.write(np.where(np.isnan(idx), -1, idx).astype("int16"), 1)
            dst.update_tags(classes=",".join(names), method=tf.METHOD_VERSION)
    return out_png
