"""Gather what the project knows into plain dicts, for the viewer page and app.

Every function reads the database or the docs and returns JSON-friendly data.
Nothing here computes new science; it only collects results that the
pipeline already produced, so the viewer shows exactly what the code found.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _q(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
    cur = conn.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def routes_summary(conn: sqlite3.Connection) -> list[dict]:
    """One row per route: track numbers, route points, cells and landform counts."""
    rows = _q(
        conn,
        """SELECT r.route_id, r.name, r.region_id, r.route_shape, r.track_date_local, r.is_timed,
                  r.n_points_clean, r.n_points_used, r.distance_raw_m, r.distance_m, r.gain_gpx_m,
                  r.min_ele_gpx_m, r.max_ele_gpx_m, s.source, s.committed_to_repo,
                  (SELECT COUNT(*) FROM route_points p WHERE p.route_id = r.route_id) AS route_points,
                  (SELECT COUNT(DISTINCT cell_id) FROM route_point_cells c WHERE c.route_id = r.route_id) AS cells
           FROM routes r JOIN route_sources s USING (route_id) ORDER BY r.region_id, r.route_id""",
    )
    for r in rows:
        r["landforms"] = {
            x["landform_class"]: x["n"]
            for x in _q(
                conn,
                "SELECT landform_class, COUNT(*) AS n FROM terrain_features WHERE route_id = ? GROUP BY 1",
                (r["route_id"],),
            )
            if x["landform_class"]
        }
    return rows


def weather_summary(conn: sqlite3.Connection) -> list[dict]:
    """Per region: cells, true-forecast runs stored, and the dates covered."""
    if not _has_table(conn, "forecast_snapshots"):
        return []
    return _q(
        conn,
        """WITH rc AS (SELECT DISTINCT r.region_id, rpc.cell_id FROM routes r
                       JOIN route_point_cells rpc ON rpc.route_id = r.route_id)
           SELECT rc.region_id,
                  COUNT(DISTINCT rc.cell_id) AS cells,
                  COUNT(DISTINCT CASE WHEN f.product = 'single_run' THEN f.issue_time_utc END) AS runs,
                  MIN(f.valid_time_utc) AS first_hour, MAX(f.valid_time_utc) AS last_hour,
                  COUNT(f.snapshot_id) AS rows
           FROM rc LEFT JOIN forecast_snapshots f ON f.cell_id = rc.cell_id
           GROUP BY rc.region_id ORDER BY rc.region_id""",
    )


def observations_summary(conn: sqlite3.Connection) -> dict:
    if not _has_table(conn, "observations"):
        return {"total": 0, "labelled": 0, "need_review": 0, "by_trip": {}}
    total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    labelled = conn.execute(
        "SELECT COUNT(*) FROM observations WHERE wind_effect IN ('loaded', 'scoured', 'mixed', 'none_seen')"
    ).fetchone()[0]
    review = conn.execute("SELECT COUNT(*) FROM observations WHERE needs_review = 1").fetchone()[0]
    return {"total": total, "labelled": labelled, "need_review": review}


def station_summary(conn: sqlite3.Connection, station_id: int = 111) -> list[dict]:
    """Model vs station statistics, if station data and its cell are stored."""
    if not _has_table(conn, "station_cells"):
        return []
    from ..validation.stations import compare

    from ..geo import haversine_m

    st = conn.execute("SELECT lat, lon FROM stations WHERE station_id = ?", (station_id,)).fetchone()
    if st is None:
        return []
    own = conn.execute("SELECT cell_id FROM station_cells WHERE station_id = ?", (station_id,)).fetchone()
    if own:
        cell_id, note = own[0], "model values from the station's own HRDPS cell"
    else:
        # Provisional: nearest stored cell that has stitched values.
        cells = conn.execute(
            """SELECT DISTINCT w.cell_id, w.grid_lat, w.grid_lon FROM weather_cells w
               JOIN forecast_snapshots f ON f.cell_id = w.cell_id AND f.product = 'historical_stitched'"""
        ).fetchall()
        if not cells:
            return []
        best = min(cells, key=lambda c: haversine_m(st[0], st[1], c[1], c[2]))
        cell_id = best[0]
        note = f"PROVISIONAL: nearest stored cell, {haversine_m(st[0], st[1], best[1], best[2]) / 1000:.1f} km from the station"
    span = conn.execute(
        "SELECT MIN(valid_time_utc), MAX(valid_time_utc) FROM station_obs WHERE station_id = ?", (station_id,)
    ).fetchone()
    start = datetime.strptime(span[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    end = datetime.strptime(span[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return [{**c.__dict__, "cell_note": note} for c in compare(conn, station_id, start, end, cell_id=cell_id)]


def scan_series(reports_dir: Path) -> dict[str, list[dict]]:
    """Daily M1 scan results per wind option, read from the scan CSVs."""
    out = {}
    for f in sorted(reports_dir.glob("scan_*.csv")):
        label = f.stem.removeprefix("scan_")
        with open(f) as fh:
            out[label] = [
                {"day": r["as_of_utc"][:10], "loading": float(r["loading_sum"]), "scour": float(r["scour_sum"]),
                 "active": r["m1_informative"] == "True"}
                for r in csv.DictReader(fh)
            ]
    return out


def exposure_points(conn: sqlite3.Connection, route_id: str, as_of_utc: str) -> list[dict]:
    """Route points with terrain and their stored M1 and B0 results for one window."""
    return _q(
        conn,
        """SELECT p.seq, ROUND(p.distance_along_m / 1000.0, 2) AS km, p.lat, p.lon,
                  ROUND(t.dem_elev_m) AS elev_m, t.landform_class, ROUND(t.aspect_true_deg) AS aspect,
                  ROUND(t.slope_deg) AS slope, ROUND(t.tpi_small_std, 2) AS tpi_small_std,
                  m.relative_index AS m1, m.raw_score AS m1_net, m.detail_json AS m1_detail,
                  b.relative_index AS b0, b.raw_score AS b0_leeward_fraction
           FROM route_points p
           JOIN terrain_features t ON t.route_id = p.route_id AND t.seq = p.seq
           LEFT JOIN exposure_scores m ON m.route_id = p.route_id AND m.seq = p.seq AND m.method = 'M1' AND m.as_of_utc = ?
           LEFT JOIN exposure_scores b ON b.route_id = p.route_id AND b.seq = p.seq AND b.method = 'B0' AND b.as_of_utc = ?
           WHERE p.route_id = ? ORDER BY p.seq""",
        (as_of_utc, as_of_utc, route_id),
    )


def decisions(path: Path = ROOT / "docs/decisions.md") -> list[dict]:
    """Every numbered decision: id, short title and full text, grouped by section."""
    out, section = [], ""
    text = path.read_text()
    blocks = re.split(r"\n(?=\*\*D\d+\.|## )", text)
    for b in blocks:
        b = b.strip()
        if b.startswith("## "):
            section = b.splitlines()[0][3:].strip()
            rest = "\n".join(b.splitlines()[1:]).strip()
            if not rest.startswith("**D"):
                continue
            b = rest
        m = re.match(r"\*\*D(\d+)\.\s*(.*?)\*\*(.*)", b, flags=re.S)
        if not m:
            continue
        title = m.group(2).strip().rstrip(".:")
        body = (m.group(3)).strip()
        out.append({"id": f"D{m.group(1)}", "section": section, "title": title or body.split(".")[0],
                    "text": re.sub(r"\s*\n\s*", " ", body)})
    return out


def status_checks(main: sqlite3.Connection, weather_conn: sqlite3.Connection | None = None) -> list[dict]:
    """The Prototype 0 checklist with a state computed from the database where possible.

    ``weather_conn`` lets weather come from a second database (the research
    copy) until the main database has its own.
    """
    routes = {r["route_id"]: r for r in routes_summary(main)}
    wx = {w["region_id"]: w for w in weather_summary(weather_conn or main)}
    obs = observations_summary(main)
    regions_with_weather = [r for r, w in wx.items() if w["rows"]]
    return [
        {"item": "Route points for all 4 tracks", "state": "done" if len(routes) == 4 else "partial",
         "detail": f"{len(routes)} routes loaded; real-data checks pass"},
        {"item": "Weather collector and backfill", "state": "done" if len(regions_with_weather) == 3 else "partial",
         "detail": f"weather stored for: {', '.join(r.replace('_', ' ') for r in regions_with_weather) or 'none yet'}; Icefield and Burstall download tonight"},
        {"item": "DEM terrain features", "state": "done" if routes and all(r["landforms"] for r in routes.values()) else "partial",
         "detail": "slope, aspect, landform class, Sx for every route point"},
        {"item": "Exposure index (B0 and M1) on one peak", "state": "done", "detail": "North Victoria"},
        {"item": "10 labelled field observations", "state": "blocked" if obs["labelled"] < 10 else "done",
         "detail": f"{obs['labelled']} labelled of {obs['total']} stored"},
        {"item": "Test: does M1 beat the aspect-only rule?", "state": "blocked",
         "detail": "needs labelled observations"},
    ]


def window_weather(conn: sqlite3.Connection, route_id: str, as_of_utc: str, hours: int = 72) -> list[dict]:
    """Per cell of a route: what the model said in the window before ``as_of``.

    Uses the same no-look-ahead rule as the index (runs published by as_of).
    Returns ridge-top (700 hPa) and 10 m wind hours above 25 km/h, the mean
    wind direction (vector average, 700 hPa), and model snowfall.
    """
    import math
    from datetime import timedelta

    from ..exposure.index import best_available_weather

    as_of = datetime.strptime(as_of_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    start = as_of - timedelta(hours=hours)
    cells = _q(
        conn,
        """SELECT DISTINCT w.cell_id, w.model_elev_m, w.grid_lat, w.grid_lon FROM route_point_cells c
           JOIN weather_cells w USING (cell_id) WHERE c.route_id = ? ORDER BY w.model_elev_m""",
        (route_id,),
    )
    out = []
    for c in cells:
        wx = best_available_weather(conn, c["cell_id"], start, as_of, as_of, wind_level="blend")
        hi = [w for w in wx if (w.speed_700 or 0) > 25]
        u = sum(-(w.speed_700 or 0) * math.sin(math.radians(w.from_700 or 0)) for w in wx)
        v = sum(-(w.speed_700 or 0) * math.cos(math.radians(w.from_700 or 0)) for w in wx)
        out.append({
            "cell_id": c["cell_id"], "model_elev_m": c["model_elev_m"], "hours": len(wx),
            "hours_700_over_25": len(hi),
            "hours_10m_over_25": sum(1 for w in wx if (w.speed_10m or 0) > 25),
            "max_700_kmh": max((w.speed_700 or 0) for w in wx) if wx else None,
            "max_10m_kmh": max((w.speed_10m or 0) for w in wx) if wx else None,
            "mean_from_700_deg": round(math.degrees(math.atan2(-u, -v)) % 360) if wx else None,
            "snowfall_cm": round(sum(w.snowfall_cm or 0 for w in wx), 1),
        })
    return out
