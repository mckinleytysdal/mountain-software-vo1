"""SQLite database: schema and connection.

Analogy: the database is a trip logbook with several sheets (tables). Each
sheet has fixed columns. A "primary key" is the column (or columns) that
names one row uniquely, like a route name plus marker number. A "foreign
key" says "this value must exist on another sheet", like "every route must
belong to a region that is listed on the regions sheet".

The schema grows one module at a time. Each step is a "migration": a block
of SQL applied once, in order. SQLite keeps the number of the last applied
step in ``PRAGMA user_version``, so running ``connect`` again never re-applies
a step.

All times are stored as ISO 8601 text in UTC, e.g. ``2026-10-16T10:59:00Z``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("data/processed/mountain.sqlite")

MIGRATIONS: list[str] = [
    # 1: Module 1, route points
    """
    CREATE TABLE regions (
        region_id   TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        notes       TEXT
    );

    CREATE TABLE peaks (
        peak_id            TEXT PRIMARY KEY,
        name               TEXT NOT NULL,
        region_id          TEXT NOT NULL REFERENCES regions(region_id),
        published_elev_m   REAL,
        elev_source        TEXT,
        is_11000er         INTEGER NOT NULL DEFAULT 0 CHECK (is_11000er IN (0, 1)),
        notes              TEXT
    );

    CREATE TABLE routes (
        route_id            TEXT PRIMARY KEY,
        name                TEXT NOT NULL,
        region_id           TEXT NOT NULL REFERENCES regions(region_id),
        peak_id             TEXT REFERENCES peaks(peak_id),
        route_shape         TEXT NOT NULL CHECK (route_shape IN ('one_way', 'out_and_back', 'loop')),
        track_date_utc      TEXT,
        is_timed            INTEGER NOT NULL CHECK (is_timed IN (0, 1)),
        n_points_raw        INTEGER NOT NULL,
        n_points_clean      INTEGER NOT NULL,
        n_points_used       INTEGER NOT NULL,
        distance_raw_m      REAL NOT NULL,
        distance_m          REAL NOT NULL,
        gain_gpx_m          REAL,
        min_ele_gpx_m       REAL,
        max_ele_gpx_m       REAL,
        gain_threshold_m    REAL NOT NULL,
        thin_interval_s     REAL,
        method_version      TEXT NOT NULL,
        loaded_at_utc       TEXT NOT NULL,
        notes               TEXT
    );

    CREATE TABLE route_sources (
        route_id                TEXT PRIMARY KEY REFERENCES routes(route_id) ON DELETE CASCADE,
        source                  TEXT NOT NULL,
        source_url              TEXT,
        file_name               TEXT NOT NULL,
        file_sha256             TEXT NOT NULL,
        download_date           TEXT NOT NULL,
        terms_note              TEXT NOT NULL,
        gpx_creator             TEXT,
        gpx_copyright_author    TEXT,
        gpx_licence             TEXT,
        redistribution_allowed  INTEGER NOT NULL CHECK (redistribution_allowed IN (0, 1)),
        committed_to_repo       INTEGER NOT NULL CHECK (committed_to_repo IN (0, 1))
    );

    CREATE TABLE route_points (
        route_id           TEXT NOT NULL REFERENCES routes(route_id) ON DELETE CASCADE,
        seq                INTEGER NOT NULL,
        distance_along_m   REAL NOT NULL,
        lat                REAL NOT NULL,
        lon                REAL NOT NULL,
        ele_gpx_m          REAL,
        time_utc           TEXT,
        method_version     TEXT NOT NULL,
        PRIMARY KEY (route_id, seq)
    );
    """,
]


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open (or create) the database and bring its schema up to date."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any migrations not yet applied. Returns the schema version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, sql in enumerate(MIGRATIONS, start=1):
        if number <= current:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {number}")
    return conn.execute("PRAGMA user_version").fetchone()[0]


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}
