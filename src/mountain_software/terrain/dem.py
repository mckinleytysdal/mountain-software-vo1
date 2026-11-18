"""Fetch a DEM window and look up route points in it.

Source: NRCan MRDEM-30 DTM (Medium Resolution Digital Elevation Model, 30 m,
bare-earth "terrain" model, not the surface model with trees). One
cloud-optimised GeoTIFF covers Canada, so a small window can be read over
HTTP without downloading the whole country. Licence: Open Government Licence
- Canada 2.0. Projection: EPSG:3979 (Canada Atlas Lambert), metres.

The window is cached in git-ignored ``data/raw/dem/`` so later runs and the
maps read the same bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

MRDEM_DTM_URL = "https://canelevation-dem.s3.ca-central-1.amazonaws.com/mrdem-30/mrdem-30-dtm.tif"
MRDEM = {
    "dem_name": "NRCan MRDEM-30 DTM",
    "url": MRDEM_DTM_URL,
    "licence": "Open Government Licence - Canada 2.0",
    "stac": "https://datacube.services.geo.ca/stac/api/collections/mrdem-30",
}
DEFAULT_DEM_DIR = Path("data/raw/dem")


@dataclass
class DemGrid:
    """Heights plus where the grid sits on Earth.

    ``transform`` is the 6-number affine transform (rasterio/GDAL style):
    x = a*col + b*row + c, y = d*col + e*row + f, for the top-left corner of
    a cell. NaN marks missing heights.
    """

    z: np.ndarray
    transform: tuple[float, float, float, float, float, float]
    crs: str
    res_m: float
    meta: dict

    def rowcol(self, x: float, y: float) -> tuple[float, float]:
        """Fractional (row, col) of the cell CENTRE grid that contains (x, y)."""
        a, b, c, d, e, f = self.transform
        # Invert the affine transform (b and d are 0 for north-up grids).
        col = (x - c) / a - 0.5
        row = (y - f) / e - 0.5
        return row, col


def _gdal_env() -> dict[str, str]:
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_TIMEOUT": "60"}
    for var in ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        if os.environ.get(var):
            env["CURL_CA_BUNDLE"] = os.environ[var]
            break
    return env


def fetch_window(
    west: float,
    south: float,
    east: float,
    north: float,
    name: str,
    dem_dir: Path = DEFAULT_DEM_DIR,
    url: str = MRDEM_DTM_URL,
    refresh: bool = False,
) -> Path:
    """Read a lon/lat box from the national DEM and save it as a GeoTIFF.

    Returns the cached file path. If the file exists it is reused unless
    ``refresh`` is True.
    """
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    dem_dir.mkdir(parents=True, exist_ok=True)
    out = dem_dir / f"{name}.tif"
    if out.exists() and not refresh:
        return out
    with rasterio.Env(**_gdal_env()), rasterio.open(f"/vsicurl/{url}") as src:
        bounds = transform_bounds("EPSG:4326", src.crs, west, south, east, north)
        window = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
        data = src.read(1, window=window)
        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            transform=src.window_transform(window),
            compress="deflate",
            tiled=False,
        )
        for key in ("blockxsize", "blockysize", "interleave"):
            profile.pop(key, None)
        with rasterio.open(out, "w", **profile) as dst:
            dst.write(data, 1)
            dst.update_tags(
                source_url=url,
                fetched_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                request_bounds_wgs84=json.dumps([west, south, east, north]),
            )
    return out


def read_grid(path: Path, meta: dict | None = None) -> DemGrid:
    import rasterio

    with rasterio.open(path) as src:
        z = src.read(1).astype("float64")
        if src.nodata is not None:
            z[z == src.nodata] = np.nan
        t = src.transform
        tags = src.tags()
        info = {
            **MRDEM,
            **(meta or {}),
            "path": str(path),
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "fetched_at_utc": tags.get("fetched_at_utc"),
            "request_bounds_wgs84": tags.get("request_bounds_wgs84"),
        }
        return DemGrid(
            z=z,
            transform=(t.a, t.b, t.c, t.d, t.e, t.f),
            crs=src.crs.to_string(),
            res_m=float(abs(t.a)),
            meta=info,
        )


def project_points(lons: list[float], lats: list[float], crs: str) -> tuple[list[float], list[float]]:
    from rasterio.warp import transform

    xs, ys = transform("EPSG:4326", crs, lons, lats)
    return list(xs), list(ys)


def convergence_deg(lons: list[float], lats: list[float], crs: str) -> list[float]:
    """Grid convergence at each point: angle from grid north to true north."""
    from .features import convergence_from_points

    x0, y0 = project_points(lons, lats, crs)
    x1, y1 = project_points(lons, [la + 0.001 for la in lats], crs)
    return [convergence_from_points(a, b, c, d) for a, b, c, d in zip(x0, y0, x1, y1)]
