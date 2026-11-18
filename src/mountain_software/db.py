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
    # 2: Module 2, weather cells and forecasts
    """
    -- One row per model grid cell. The cell is named by the grid coordinates
    -- the API returns, never by the coordinates we asked for.
    CREATE TABLE weather_cells (
        cell_id          INTEGER PRIMARY KEY,
        model            TEXT NOT NULL,
        grid_lat         REAL NOT NULL,
        grid_lon         REAL NOT NULL,
        model_elev_m     REAL,
        first_seen_utc   TEXT NOT NULL,
        UNIQUE (model, grid_lat, grid_lon)
    );

    -- Which cell each route point falls in.
    CREATE TABLE route_point_cells (
        route_id             TEXT NOT NULL,
        seq                  INTEGER NOT NULL,
        model                TEXT NOT NULL,
        cell_id              INTEGER NOT NULL REFERENCES weather_cells(cell_id),
        distance_to_cell_m   REAL NOT NULL,
        ele_offset_gpx_m     REAL,
        method_version       TEXT NOT NULL,
        PRIMARY KEY (route_id, seq, model),
        FOREIGN KEY (route_id, seq) REFERENCES route_points(route_id, seq) ON DELETE CASCADE
    );

    -- One row per HTTP request to a weather API, pointing at the raw file.
    CREATE TABLE weather_fetches (
        fetch_id          INTEGER PRIMARY KEY,
        endpoint          TEXT NOT NULL,
        product           TEXT NOT NULL,
        model             TEXT NOT NULL,
        params_json       TEXT NOT NULL,
        raw_path          TEXT NOT NULL,
        raw_sha256        TEXT NOT NULL,
        fetched_at_utc    TEXT NOT NULL,
        issue_time_utc    TEXT,
        issue_time_note   TEXT NOT NULL,
        units_json        TEXT,
        missing_json      TEXT,
        n_locations       INTEGER NOT NULL
    );

    -- Hourly model values per cell.
    --   product 'single_run'           one model run; issue_time_utc is the true run (initialisation) time
    --   product 'historical_stitched'  first hours of successive runs glued together; issue time unknown
    CREATE TABLE forecast_snapshots (
        snapshot_id              INTEGER PRIMARY KEY,
        cell_id                  INTEGER NOT NULL REFERENCES weather_cells(cell_id),
        model                    TEXT NOT NULL,
        product                  TEXT NOT NULL CHECK (product IN ('single_run', 'historical_stitched')),
        issue_time_utc           TEXT,
        issue_time_known         INTEGER NOT NULL CHECK (issue_time_known IN (0, 1)),
        issue_key                TEXT GENERATED ALWAYS AS (COALESCE(issue_time_utc, 'unknown')) VIRTUAL,
        valid_time_utc           TEXT NOT NULL,
        lead_hours               REAL,
        temperature_2m_c         REAL,
        wind_speed_10m_kmh       REAL,
        wind_direction_10m_deg   REAL,
        wind_gusts_10m_kmh       REAL,
        snowfall_cm              REAL,
        precipitation_mm         REAL,
        fetch_id                 INTEGER NOT NULL REFERENCES weather_fetches(fetch_id),
        method_version           TEXT NOT NULL,
        CHECK ((product = 'single_run' AND issue_time_utc IS NOT NULL AND issue_time_known = 1 AND lead_hours IS NOT NULL)
            OR (product = 'historical_stitched' AND issue_time_utc IS NULL AND issue_time_known = 0 AND lead_hours IS NULL))
    );
    CREATE UNIQUE INDEX forecast_snapshots_one_value
        ON forecast_snapshots (cell_id, model, product, issue_key, valid_time_utc);
    CREATE INDEX forecast_snapshots_valid ON forecast_snapshots (valid_time_utc);
    """,
    # 3: Module 3, DEM terrain features
    """
    CREATE TABLE dem_sources (
        dem_id                 INTEGER PRIMARY KEY,
        name                   TEXT NOT NULL,
        url                    TEXT NOT NULL,
        licence                TEXT NOT NULL,
        crs                    TEXT NOT NULL,
        res_m                  REAL NOT NULL,
        path                   TEXT NOT NULL,
        sha256                 TEXT NOT NULL UNIQUE,
        fetched_at_utc         TEXT,
        request_bounds_wgs84   TEXT
    );

    -- Terrain at each route point. Elevation here is DEM elevation, the one
    -- to use for terrain work (GPX elevation stays in route_points).
    CREATE TABLE terrain_features (
        route_id            TEXT NOT NULL,
        seq                 INTEGER NOT NULL,
        dem_id              INTEGER NOT NULL REFERENCES dem_sources(dem_id),
        dem_elev_m          REAL,
        slope_deg           REAL,
        aspect_true_deg     REAL,
        convergence_deg     REAL NOT NULL,
        curvature_per_m     REAL,
        tpi_small_m         REAL,
        tpi_large_m         REAL,
        tpi_small_std       REAL,
        tpi_large_std       REAL,
        slope_position      TEXT,
        landform_class      TEXT,
        surface_class       TEXT NOT NULL DEFAULT 'unknown',
        params_json         TEXT NOT NULL,
        method_version      TEXT NOT NULL,
        PRIMARY KEY (route_id, seq, dem_id),
        FOREIGN KEY (route_id, seq) REFERENCES route_points(route_id, seq) ON DELETE CASCADE
    );

    -- Maximum upwind slope (Sx) for each route point and wind direction.
    CREATE TABLE route_point_sx (
        route_id             TEXT NOT NULL,
        seq                  INTEGER NOT NULL,
        dem_id               INTEGER NOT NULL REFERENCES dem_sources(dem_id),
        dmax_m               REAL NOT NULL,
        wind_from_true_deg   REAL NOT NULL,
        sx_deg               REAL,
        method_version       TEXT NOT NULL,
        PRIMARY KEY (route_id, seq, dem_id, dmax_m, wind_from_true_deg),
        FOREIGN KEY (route_id, seq) REFERENCES route_points(route_id, seq) ON DELETE CASCADE
    );
    """,
    # 4: Module 4, relative exposure to potential wind loading
    """
    CREATE TABLE exposure_scores (
        route_id            TEXT NOT NULL,
        seq                 INTEGER NOT NULL,
        method              TEXT NOT NULL CHECK (method IN ('B0', 'M1')),
        method_version      TEXT NOT NULL,
        as_of_utc           TEXT NOT NULL,
        window_start_utc    TEXT NOT NULL,
        window_end_utc      TEXT NOT NULL,
        data_age_hours      REAL,
        inputs_json         TEXT NOT NULL,
        raw_score           REAL,
        relative_index      REAL CHECK (relative_index IS NULL OR (relative_index >= 0 AND relative_index <= 1)),
        detail_json         TEXT,
        created_at_utc      TEXT NOT NULL,
        PRIMARY KEY (route_id, seq, method, method_version, as_of_utc),
        FOREIGN KEY (route_id, seq) REFERENCES route_points(route_id, seq) ON DELETE CASCADE
    );
    """,
    # 5: 700 hPa (about ridge-top height) wind, height and temperature
    """
    ALTER TABLE forecast_snapshots ADD COLUMN wind_speed_700hpa_kmh REAL;
    ALTER TABLE forecast_snapshots ADD COLUMN wind_direction_700hpa_deg REAL;
    ALTER TABLE forecast_snapshots ADD COLUMN geopotential_height_700hpa_m REAL;
    ALTER TABLE forecast_snapshots ADD COLUMN temperature_700hpa_c REAL;
    ALTER TABLE weather_fetches ADD COLUMN variables TEXT;
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
