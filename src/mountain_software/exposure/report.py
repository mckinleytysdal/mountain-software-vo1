"""Write the exposure result as plain text and a map, following the wording rules.

Every report includes: what was computed and how (evidence), how old the
weather data is (data age), what is uncertain, and a link to the official
Avalanche Canada forecast. It never uses the words the project forbids, and
it calls the output "relative exposure to potential wind loading".
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

AVCAN_URL = "https://avalanche.ca/forecasts"
LABEL = "relative exposure to potential wind loading"


def _rows(conn: sqlite3.Connection, route_id: str, as_of: str, method: str):
    return conn.execute(
        """SELECT e.seq, e.raw_score, e.relative_index, e.detail_json, e.data_age_hours, e.inputs_json,
                  e.window_start_utc, e.window_end_utc, e.method_version,
                  t.landform_class, t.aspect_true_deg, t.dem_elev_m, p.distance_along_m
           FROM exposure_scores e
           JOIN terrain_features t ON t.route_id = e.route_id AND t.seq = e.seq
           JOIN route_points p ON p.route_id = e.route_id AND p.seq = e.seq
           WHERE e.route_id = ? AND e.as_of_utc = ? AND e.method = ? ORDER BY e.seq""",
        (route_id, as_of, method),
    ).fetchall()


def agreement(conn: sqlite3.Connection, route_id: str, as_of: str) -> dict:
    """How often B0 and M1 agree on which points are in the upper half."""
    m1 = {r["seq"]: r["relative_index"] for r in _rows(conn, route_id, as_of, "M1")}
    b0 = {r["seq"]: r["relative_index"] for r in _rows(conn, route_id, as_of, "B0")}
    both = [s for s in m1 if m1[s] is not None and b0.get(s) is not None]
    if not both:
        return {"points": 0}
    same = sum((m1[s] >= 0.5) == (b0[s] >= 0.5) for s in both)
    import numpy as np

    a = np.array([m1[s] for s in both])
    b = np.array([b0[s] for s in both])
    corr = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else None
    return {"points": len(both), "same_half_fraction": same / len(both), "rank_correlation": corr}


def render_markdown(conn: sqlite3.Connection, route_id: str, as_of: str, top_n: int = 8) -> str:
    rows = _rows(conn, route_id, as_of, "M1")
    if not rows:
        raise ValueError("no exposure scores for that route and time")
    first = rows[0]
    inputs = json.loads(first["inputs_json"])
    params = inputs["params"]
    age = first["data_age_hours"]
    stitched = inputs["stitched_fraction"]
    agree = agreement(conn, route_id, as_of)
    top = sorted((r for r in rows if r["relative_index"] is not None), key=lambda r: -r["relative_index"])[:top_n]
    no_transport = all((r["raw_score"] or 0.0) == 0.0 for r in rows)

    lines = [
        f"# {route_id}: {LABEL}",
        "",
        f"Window: {first['window_start_utc']} to {first['window_end_utc']} (UTC). Method {first['method_version']}.",
        "",
        "This is an exploratory research output. It ranks route points against each other; it is not a hazard",
        "rating, not an official warning and not a verified observation. Read the official forecast:",
        f"[Avalanche Canada]({AVCAN_URL}).",
        "",
        "## Data age",
        "",
        f"- Newest model run used: {inputs['newest_issue_time_utc'] or 'none (issue time unknown)'}",
        f"- Data age at the end of the window: {age:.0f} h" if age is not None else "- Data age: unknown",
        f"- Share of hours from the stitched archive (issue time unknown): {stitched:.0%}",
        "",
        "## Evidence",
        "",
        "- Weather: GEM HRDPS 2.5 km via Open-Meteo, raw model cell values (no elevation adjustment).",
        "- Terrain: NRCan MRDEM-30 (30 m); shelter from maximum upwind slope (Sx), "
        f"{params['sx_dmax_m']:.0f} m search distance.",
        f"- Transport assumed above {params['transport_threshold_kmh']:.0f} km/h ({params.get('wind_level', '10m')} wind), growing with the "
        f"power {params['transport_exponent']:.0f}; snow supply from snowfall in the previous "
        f"{params['fresh_snow_hours']} h.",
        "",
    ]
    if no_transport or not top:
        lines += [
            "**No result for this window.** No hour had model wind above the transport threshold with snow",
            "available, so M1 cannot separate route points. Model wind is smoothed and may under-read ridge",
            "wind; this does not show that no snow moved.",
        ]
    else:
        lines += [
            f"Route points with the highest {LABEL} (1 = highest on this route):",
            "",
            "| km | DEM elev (m) | landform | aspect (true) | index |",
            "|---:|---:|---|---:|---:|",
        ]
    for r in top:
        asp = f"{r['aspect_true_deg']:.0f}°" if r["aspect_true_deg"] is not None else "flat"
        lines.append(
            f"| {r['distance_along_m'] / 1000:.2f} | {r['dem_elev_m']:.0f} | {(r['landform_class'] or '').replace('_', ' ')} | {asp} | {r['relative_index']:.2f} |"
        )
    lines += [
        "",
        "## Baseline comparison",
        "",
        f"B0 (aspect-only) and M1 put the same points in the upper half for "
        f"{agree.get('same_half_fraction', 0):.0%} of {agree.get('points', 0)} points"
        + (f"; rank correlation {agree['rank_correlation']:.2f}." if agree.get("rank_correlation") is not None else "."),
        "",
        "## Uncertainty",
        "",
        "- No observations have been used to check this index yet. It is untested.",
        "- Model wind is wind over a smoothed model surface, often hundreds of metres below ridge crests.",
        "- The transport threshold and exponent are literature-based guesses, not fitted values.",
        "- A 30 m DEM misses small features (cornices, small gullies, boulder fields).",
        "- Surface type (glacier, rock, snow cover) is not known and is ignored.",
        "",
        f"Weather data by Open-Meteo.com (CC BY 4.0). DEM: NRCan MRDEM-30 (OGL-Canada 2.0). Official forecasts: {AVCAN_URL}",
    ]
    return "\n".join(lines) + "\n"


def exposure_map(conn: sqlite3.Connection, route_id: str, as_of: str, dem_path: Path, out_png: Path) -> Path:
    """Route points coloured by M1 relative index on a hillshade.

    Colour scale: white to purple-blue (matplotlib 'PuBu'), a single-hue ramp
    that does not resemble the danger scale.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from ..terrain import dem as demmod
    from ..terrain.maps import hillshade

    grid = demmod.read_grid(dem_path)
    a, _, c, _, e, f = grid.transform
    h, w = grid.z.shape
    extent = (c, c + a * w, f + e * h, f)
    rows = conn.execute(
        """SELECT p.lat, p.lon, e.relative_index FROM exposure_scores e
           JOIN route_points p ON p.route_id = e.route_id AND p.seq = e.seq
           WHERE e.route_id = ? AND e.as_of_utc = ? AND e.method = 'M1' ORDER BY e.seq""",
        (route_id, as_of),
    ).fetchall()
    xs, ys = demmod.project_points([r[1] for r in rows], [r[0] for r in rows], grid.crs)
    vals = [r[2] if r[2] is not None else float("nan") for r in rows]

    fig, ax = plt.subplots(figsize=(9, 7), dpi=150)
    ax.imshow(hillshade(grid.z, grid.res_m), cmap="gray", extent=extent, vmin=0, vmax=1)
    ax.plot(xs, ys, color="black", lw=0.8, alpha=0.6)
    sc = ax.scatter(xs, ys, c=vals, cmap="PuBu", vmin=0, vmax=1, s=42, edgecolors="black", linewidths=0.5, zorder=3)
    cb = fig.colorbar(sc, ax=ax, shrink=0.7)
    cb.set_label(f"{LABEL}\n(rank within this route, 0 to 1)", fontsize=8)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{route_id}: {LABEL}, window ending {as_of}", fontsize=10)
    fig.text(
        0.01,
        0.02,
        "Exploratory research output, untested against observations. Not a hazard rating or an official warning. "
        f"Official forecasts: {AVCAN_URL}. Weather: Open-Meteo.com (CC BY 4.0), GEM HRDPS. DEM: NRCan MRDEM-30.",
        fontsize=6.5,
        wrap=True,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)
    return out_png
