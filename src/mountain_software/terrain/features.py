"""Terrain features from a DEM grid. Pure numpy: no files, no network.

A DEM (digital elevation model) is a grid of heights, like graph paper where
each square holds the ground height at that spot. Here each square ("cell")
is 30 m wide. Row 0 is the north edge of the grid, column 0 the west edge.

Conventions used everywhere in this module:

* ``z`` is a 2-D float array of heights in metres; missing cells are NaN.
* ``res_m`` is the cell size in metres.
* Directions are compass degrees: 0 = north, 90 = east, clockwise.
* "Grid north" is straight up the array. In a Lambert projection such as
  EPSG:3979, grid north is rotated from true north by the "grid convergence"
  angle. Aspect and wind direction must be converted before comparing them.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

METHOD_VERSION = "terrain-v2"


def _pad_edge(z: np.ndarray) -> np.ndarray:
    return np.pad(z, 1, mode="edge")


def slope_aspect_horn(z: np.ndarray, res_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Slope (degrees) and aspect (degrees from grid north) by Horn's method.

    Horn (1981) estimates the east-west and north-south height change at a
    cell from its 8 neighbours, weighting the 4 nearest neighbours twice:

        a b c
        d e f      dz/dx = ((c + 2f + i) - (a + 2d + g)) / (8 * res)
        g h i      dz/dy = ((g + 2h + i) - (a + 2b + c)) / (8 * res)

    (dz/dy here is the height change going SOUTH, because row numbers grow
    southwards.) Slope is the steepness; aspect is the compass direction the
    slope faces, i.e. the way water would run off it. Flat cells get aspect NaN.
    """
    p = _pad_edge(z)
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * res_m)  # rise going east
    dzdy_south = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * res_m)  # rise going south
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy_south)))
    # Downslope direction: east component -dzdx, north component +dzdy_south.
    aspect = np.degrees(np.arctan2(-dzdx, dzdy_south)) % 360.0
    flat = np.hypot(dzdx, dzdy_south) < 1e-9
    aspect = np.where(flat, np.nan, aspect)
    return slope, aspect


def laplacian_curvature(z: np.ndarray, res_m: float) -> np.ndarray:
    """Curvature as minus the Laplacian, in 1/m.

    Positive = convex (a bump or ridge: neighbours lower than the centre),
    negative = concave (a hollow, gully or bowl). This is the simple
    "general curvature"; profile and plan curvature can come later.
    """
    p = _pad_edge(z)
    lap = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4 * p[1:-1, 1:-1]) / (res_m**2)
    return -lap


def _disk(radius_cells: int) -> np.ndarray:
    y, x = np.ogrid[-radius_cells : radius_cells + 1, -radius_cells : radius_cells + 1]
    return (x * x + y * y) <= radius_cells * radius_cells


def tpi(z: np.ndarray, radius_m: float, res_m: float) -> np.ndarray:
    """Topographic Position Index: height minus the mean height around it.

    Analogy: stand on a spot and compare yourself with everyone within
    ``radius_m``. Taller than the crowd (positive) = ridge or knoll; shorter
    (negative) = gully or valley. The centre cell is left out of the mean.
    NaN cells are ignored; cells with no valid neighbours get NaN.
    """
    r = max(1, int(round(radius_m / res_m)))
    k = _disk(r).astype(float)
    k[r, r] = 0.0
    valid = np.isfinite(z)
    zf = np.where(valid, z, 0.0)
    total = ndimage.convolve(zf, k, mode="constant", cval=0.0)
    count = ndimage.convolve(valid.astype(float), k, mode="constant", cval=0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / count
    out = z - mean
    out[count == 0] = np.nan
    return out


def standardise(x: np.ndarray) -> np.ndarray:
    """Turn values into "how many standard deviations from the average"."""
    mu = np.nanmean(x)
    sd = np.nanstd(x)
    return (x - mu) / sd if sd > 0 else np.zeros_like(x)


SLOPE_POSITIONS = ("valley", "lower_slope", "flat", "middle_slope", "upper_slope", "ridge")


def slope_position(tpi_std: np.ndarray, slope_deg: np.ndarray, flat_slope_deg: float = 5.0) -> np.ndarray:
    """Six slope-position classes from standardised TPI (Weiss 2001).

    ridge         TPI > +1 SD
    upper_slope   +0.5 < TPI <= +1 SD
    middle_slope  -0.5 <= TPI <= +0.5 SD and slope > ``flat_slope_deg``
    flat          -0.5 <= TPI <= +0.5 SD and slope <= ``flat_slope_deg``
    lower_slope   -1 <= TPI < -0.5 SD
    valley        TPI < -1 SD
    Returns an array of class names ('' where TPI is NaN).
    """
    out = np.full(tpi_std.shape, "", dtype=object)
    t = tpi_std
    out[t > 1.0] = "ridge"
    out[(t > 0.5) & (t <= 1.0)] = "upper_slope"
    mid = (t >= -0.5) & (t <= 0.5)
    out[mid & (slope_deg > flat_slope_deg)] = "middle_slope"
    out[mid & (slope_deg <= flat_slope_deg)] = "flat"
    out[(t >= -1.0) & (t < -0.5)] = "lower_slope"
    out[t < -1.0] = "valley"
    return out


def angular_difference(a: float, b: float) -> float:
    """Smallest angle between two compass directions (0 to 180)."""
    d = abs(a - b) % 360.0
    return 360.0 - d if d > 180.0 else d


def grid_to_true_deg(grid_deg: float | np.ndarray, convergence_deg: float | np.ndarray):
    """Convert a direction measured from grid north to one from true north.

    ``convergence_deg`` is the angle from grid north to true north, measured
    clockwise (see :func:`convergence_from_points`).
    """
    return (np.asarray(grid_deg) - convergence_deg) % 360.0


def convergence_from_points(x0: float, y0: float, x_north: float, y_north: float) -> float:
    """Angle (degrees, clockwise) from grid north to true north at a point.

    Give the projected position of the point and of a point a little further
    true-north of it. The vector between them points to true north on the
    grid; its compass angle on the grid is the convergence.
    """
    return math.degrees(math.atan2(x_north - x0, y_north - y0))


def sx_ray(
    z: np.ndarray,
    row: float,
    col: float,
    res_m: float,
    upwind_grid_deg: float,
    dmax_m: float,
) -> float:
    """Maximum upwind slope along one ray (Winstral et al. 2002), in degrees.

    Walk from the point towards where the wind comes from, out to ``dmax_m``.
    At each step compare heights: Sx is the steepest upward angle to any
    point along the way.

        Sx = max over upwind points j of atan((z_j - z_0) / distance_j)

    Positive Sx: higher ground upwind shelters the point (a lee spot where
    snow can settle). Negative Sx: the point stands above everything upwind,
    so the wind hits it fully (exposed, often scoured).
    Heights between cell centres are found by bilinear interpolation.
    """
    z0 = bilinear(z, row, col)
    if not math.isfinite(z0):
        return math.nan
    theta = math.radians(upwind_grid_deg)
    d_row = -math.cos(theta)  # moving grid north = decreasing row
    d_col = math.sin(theta)
    best = -math.inf
    step = res_m
    dist = step
    while dist <= dmax_m + 1e-9:
        r = row + d_row * dist / res_m
        c = col + d_col * dist / res_m
        zj = bilinear(z, r, c)
        if not math.isfinite(zj):
            break
        best = max(best, math.degrees(math.atan2(zj - z0, dist)))
        dist += step
    return best if best > -math.inf else math.nan


def sx(
    z: np.ndarray,
    row: float,
    col: float,
    res_m: float,
    wind_from_grid_deg: float,
    dmax_m: float,
    window_deg: float = 30.0,
    increment_deg: float = 5.0,
) -> float:
    """Sx averaged over a window of upwind directions (Winstral et al. 2002).

    Wind direction wobbles, so we compute :func:`sx_ray` for directions from
    ``wind_from - window/2`` to ``wind_from + window/2`` in ``increment_deg``
    steps and average them.
    """
    n = int(round(window_deg / increment_deg))
    dirs = [wind_from_grid_deg - window_deg / 2 + k * increment_deg for k in range(n + 1)]
    vals = [sx_ray(z, row, col, res_m, d % 360.0, dmax_m) for d in dirs]
    vals = [v for v in vals if math.isfinite(v)]
    return float(np.mean(vals)) if vals else math.nan


def bilinear(z: np.ndarray, row: float, col: float) -> float:
    """Height at a fractional (row, col) position, blending the 4 nearest cells."""
    nrows, ncols = z.shape
    if row < 0 or col < 0 or row > nrows - 1 or col > ncols - 1:
        return math.nan
    r0, c0 = int(math.floor(row)), int(math.floor(col))
    r1, c1 = min(r0 + 1, nrows - 1), min(c0 + 1, ncols - 1)
    fr, fc = row - r0, col - c0
    v = (
        z[r0, c0] * (1 - fr) * (1 - fc)
        + z[r0, c1] * (1 - fr) * fc
        + z[r1, c0] * fr * (1 - fc)
        + z[r1, c1] * fr * fc
    )
    return float(v)


LANDFORM_CLASSES = ("ridge", "couloir_gully", "basin_valley", "steep_face", "open_slope")


def landform_class(
    slope_deg: np.ndarray,
    tpi_small_std: np.ndarray,
    tpi_large_std: np.ndarray,
    steep_deg: float = 30.0,
    basin_max_slope_deg: float = 25.0,
) -> np.ndarray:
    """Rule-based landform class for each cell. First matching rule wins:

    1. ridge          small-scale TPI > +1 SD, or small-scale TPI > +0.5 SD on
                      ground that is high at the large scale (TPI > +1 SD)
    2. couloir_gully  small-scale TPI < -1 SD and slope >= ``steep_deg``
    3. basin_valley   large-scale TPI < -0.5 SD and slope < ``basin_max_slope_deg``
    4. steep_face     slope >= ``steep_deg``
    5. open_slope     everything else

    Glacier, rock and snow are SURFACE types, not landforms; they need
    glacier outlines and imagery and are stored separately (still unknown).
    """
    out = np.full(slope_deg.shape, "", dtype=object)
    valid = np.isfinite(slope_deg) & np.isfinite(tpi_small_std) & np.isfinite(tpi_large_std)
    rules = [
        ("ridge", (tpi_small_std > 1.0) | ((tpi_small_std > 0.5) & (tpi_large_std > 1.0))),
        ("couloir_gully", (tpi_small_std < -1.0) & (slope_deg >= steep_deg)),
        ("basin_valley", (tpi_large_std < -0.5) & (slope_deg < basin_max_slope_deg)),
        ("steep_face", slope_deg >= steep_deg),
        ("open_slope", np.ones_like(valid)),
    ]
    assigned = ~valid
    for name, mask in rules:
        take = mask & ~assigned
        out[take] = name
        assigned |= take
    return out
