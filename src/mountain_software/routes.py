"""Module 1 pipeline: GPX file -> cleaned, thinned track -> 250 m route points -> SQLite.

Order of steps for one track:
1. parse the GPX file
2. clean: drop impossible coordinates and back-to-back repeats
3. thin: if the track is timed (has a time on each point), keep ~1 point / 10 s
4. measure: distance, GPX elevation gain, min/max GPX elevation
5. resample: one route point every ~250 m along the track
6. store: replace this route's rows in the database (safe to rerun)
"""

from __future__ import annotations

import sqlite3
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import gpx as gpxmod
from .geo import elevation_gain_m, path_length_m
from .sampling import DEFAULT_SPACING_M, RoutePoint, resample
from .sampling import METHOD_VERSION as SAMPLING_VERSION

DEFAULT_MANIFEST = Path("data/routes/manifest.toml")
GAIN_THRESHOLD_M = 3.0
THIN_INTERVAL_S = 10.0
# A track counts as "1 Hz-ish" (needs thinning) when its typical gap is
# shorter than the thinning interval.
METHOD_VERSION = f"{gpxmod.METHOD_VERSION}+thin10s-v1+gain3m-v1+{SAMPLING_VERSION}"


@dataclass
class ProcessedTrack:
    track: gpxmod.GpxTrack
    clean: list[gpxmod.TrackPoint]
    used: list[gpxmod.TrackPoint]
    thinned: bool
    distance_raw_m: float
    distance_m: float
    gain_gpx_m: float
    min_ele_gpx_m: float | None
    max_ele_gpx_m: float | None
    route_points: list[RoutePoint] = field(default_factory=list)

    @property
    def track_date_utc(self) -> str | None:
        times = [p.time_utc for p in self.clean if p.time_utc is not None]
        return times[0].date().isoformat() if times else None


def process_track(
    track: gpxmod.GpxTrack,
    spacing_m: float = DEFAULT_SPACING_M,
    thin_interval_s: float = THIN_INTERVAL_S,
    gain_threshold_m: float = GAIN_THRESHOLD_M,
) -> ProcessedTrack:
    """Run steps 2-5 on a parsed track. Pure function: no files, no database."""
    clean = gpxmod.clean_points(track.points)
    if len(clean) < 2:
        raise gpxmod.GpxError("fewer than 2 usable points after cleaning")
    raw_dist = path_length_m([(p.lat, p.lon) for p in clean])

    interval = gpxmod.median_interval_s(clean)
    thinned = track.is_timed and interval is not None and interval < thin_interval_s
    used = gpxmod.thin_by_time(clean, thin_interval_s) if thinned else clean
    dist = path_length_m([(p.lat, p.lon) for p in used])

    eles = [p.ele_gpx_m for p in used if p.ele_gpx_m is not None]
    return ProcessedTrack(
        track=track,
        clean=clean,
        used=used,
        thinned=thinned,
        distance_raw_m=raw_dist,
        distance_m=dist,
        gain_gpx_m=elevation_gain_m((p.ele_gpx_m for p in used), gain_threshold_m),
        min_ele_gpx_m=min(eles) if eles else None,
        max_ele_gpx_m=max(eles) if eles else None,
        route_points=resample(used, spacing_m),
    )


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    with open(path, "rb") as fh:
        manifest = tomllib.load(fh)
    ids = [r["route_id"] for r in manifest.get("routes", [])]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate route_id in manifest")
    regions = {r["region_id"] for r in manifest.get("regions", [])}
    for r in manifest.get("routes", []):
        if r["region_id"] not in regions:
            raise ValueError(f"route {r['route_id']} names unknown region {r['region_id']}")
        for key in ("source", "download_date", "terms_note", "file"):
            if not str(r.get(key, "")).strip():
                raise ValueError(f"route {r['route_id']} is missing '{key}'")
    return manifest


def track_path(entry: dict[str, Any], routes_dir: Path) -> Path:
    return routes_dir / entry["file"]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upsert_regions_and_peaks(conn: sqlite3.Connection, manifest: dict[str, Any]) -> None:
    with conn:
        for r in manifest.get("regions", []):
            conn.execute(
                "INSERT INTO regions (region_id, name, notes) VALUES (?, ?, ?) "
                "ON CONFLICT(region_id) DO UPDATE SET name = excluded.name, notes = excluded.notes",
                (r["region_id"], r["name"], r.get("notes")),
            )
        for p in manifest.get("peaks", []):
            conn.execute(
                "INSERT INTO peaks (peak_id, name, region_id, published_elev_m, elev_source, is_11000er, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(peak_id) DO UPDATE SET name = excluded.name, region_id = excluded.region_id, "
                "published_elev_m = excluded.published_elev_m, elev_source = excluded.elev_source, "
                "is_11000er = excluded.is_11000er, notes = excluded.notes",
                (
                    p["peak_id"],
                    p["name"],
                    p["region_id"],
                    p.get("published_elev_m"),
                    p.get("elev_source"),
                    int(bool(p.get("is_11000er", False))),
                    p.get("notes"),
                ),
            )


def store_route(
    conn: sqlite3.Connection,
    entry: dict[str, Any],
    processed: ProcessedTrack,
    file_path: Path,
) -> None:
    """Write one route, its source row and its route points.

    Rerunning replaces the route's old rows inside one transaction, so the
    database never holds duplicates or a half-written route.
    """
    route_id = entry["route_id"]
    t = processed.track
    with conn:
        conn.execute("DELETE FROM routes WHERE route_id = ?", (route_id,))
        conn.execute(
            """INSERT INTO routes (route_id, name, region_id, peak_id, route_shape, track_date_utc,
                is_timed, n_points_raw, n_points_clean, n_points_used, distance_raw_m, distance_m,
                gain_gpx_m, min_ele_gpx_m, max_ele_gpx_m, gain_threshold_m, thin_interval_s,
                method_version, loaded_at_utc, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                route_id,
                entry["name"],
                entry["region_id"],
                entry.get("peak_id"),
                entry["route_shape"],
                processed.track_date_utc or entry.get("track_date"),
                int(t.is_timed),
                len(t.points),
                len(processed.clean),
                len(processed.used),
                processed.distance_raw_m,
                processed.distance_m,
                processed.gain_gpx_m,
                processed.min_ele_gpx_m,
                processed.max_ele_gpx_m,
                GAIN_THRESHOLD_M,
                THIN_INTERVAL_S if processed.thinned else None,
                METHOD_VERSION,
                _utc_now(),
                entry.get("notes"),
            ),
        )
        conn.execute(
            """INSERT INTO route_sources (route_id, source, source_url, file_name, file_sha256,
                download_date, terms_note, gpx_creator, gpx_copyright_author, gpx_licence,
                redistribution_allowed, committed_to_repo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                route_id,
                entry["source"],
                entry.get("source_url") or None,
                entry["file"],
                gpxmod.file_sha256(file_path),
                entry["download_date"],
                entry["terms_note"],
                t.creator,
                t.copyright_author,
                t.licence,
                int(bool(entry.get("redistribution_allowed", False))),
                int(bool(entry.get("committed_to_repo", False))),
            ),
        )
        conn.executemany(
            """INSERT INTO route_points (route_id, seq, distance_along_m, lat, lon, ele_gpx_m,
                time_utc, method_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (route_id, rp.seq, rp.distance_along_m, rp.lat, rp.lon, rp.ele_gpx_m, _iso(rp.time_utc), SAMPLING_VERSION)
                for rp in processed.route_points
            ],
        )


@dataclass
class LoadResult:
    loaded: dict[str, ProcessedTrack] = field(default_factory=dict)
    missing: dict[str, Path] = field(default_factory=dict)


def load_all(
    conn: sqlite3.Connection,
    manifest_path: Path = DEFAULT_MANIFEST,
    routes_dir: Path | None = None,
    spacing_m: float = DEFAULT_SPACING_M,
) -> LoadResult:
    """Load every track listed in the manifest whose file is present."""
    manifest = load_manifest(manifest_path)
    routes_dir = routes_dir or manifest_path.parent
    upsert_regions_and_peaks(conn, manifest)
    result = LoadResult()
    for entry in manifest.get("routes", []):
        path = track_path(entry, routes_dir)
        if not path.exists():
            result.missing[entry["route_id"]] = path
            continue
        processed = process_track(gpxmod.parse_gpx(path), spacing_m=spacing_m)
        store_route(conn, entry, processed, path)
        result.loaded[entry["route_id"]] = processed
    return result
