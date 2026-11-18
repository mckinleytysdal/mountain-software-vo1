"""Write observations to the database and link them to the nearest route point."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime

from ..geo import haversine_m
from .schema import Observation

MAX_LINK_DISTANCE_M = 300.0


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def nearest_route_point(conn: sqlite3.Connection, lat: float, lon: float, route_id: str | None = None):
    """(route_id, seq, distance_m) of the closest route point, or None if > 300 m away."""
    sql = "SELECT route_id, seq, lat, lon FROM route_points"
    args: list = []
    if route_id:
        sql += " WHERE route_id = ?"
        args.append(route_id)
    best = None
    for r in conn.execute(sql, args):
        d = haversine_m(lat, lon, r[2], r[3])
        if best is None or d < best[2]:
            best = (r[0], r[1], d)
    if best and best[2] <= MAX_LINK_DISTANCE_M:
        return best
    return None


def store_observations(conn: sqlite3.Connection, observations: list[Observation]) -> int:
    """Insert or replace observations by ``obs_key``. Returns how many were written."""
    now = _iso(datetime.now(UTC))
    with conn:
        for o in observations:
            link = nearest_route_point(conn, o.lat, o.lon, o.route_id) if o.lat is not None and o.lon is not None else None
            fields = {k: v for k, v in asdict(o).items() if k not in ("evidence", "sentence")}
            conn.execute("DELETE FROM observations WHERE obs_key = ?", (o.obs_key,))
            conn.execute(
                """INSERT INTO observations (obs_key, source_type, observer, observed_at_utc, time_precision,
                    published_at_utc, confidence, needs_review, peak_id, route_id, lat, lon, elev_m, location_note,
                    landform, aspect_deg, nearest_route_id, nearest_seq, nearest_distance_m, wind_effect,
                    is_negative, fields_json, sentence, loaded_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    o.obs_key, o.source_type, o.observer, _iso(o.observed_at_utc), o.time_precision,
                    _iso(o.published_at_utc), o.confidence, int(o.needs_review), o.peak_id, o.route_id,
                    o.lat, o.lon, o.elev_m, o.location_note, o.landform, o.aspect_deg,
                    link[0] if link else None, link[1] if link else None, link[2] if link else None,
                    o.wind_effect, int(o.is_negative), json.dumps(fields, default=str, sort_keys=True),
                    o.sentence, now,
                ),
            )
            conn.executemany(
                "INSERT INTO observation_evidence (obs_key, kind, text, url, author, published, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(o.obs_key, e.kind, e.text, e.url, e.author, e.published, e.note) for e in o.evidence],
            )
    return len(observations)
