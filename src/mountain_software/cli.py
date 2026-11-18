"""Command line entry point: ``uv run mountain <command>``."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from . import db
from .routes import DEFAULT_MANIFEST, load_all, load_manifest


def cmd_routes_load(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    result = load_all(conn, Path(args.manifest), force=args.force)
    for route_id, p in result.loaded.items():
        print(
            f"{route_id:26s} raw {p.distance_raw_m / 1000:6.2f} km  used {p.distance_m / 1000:6.2f} km  "
            f"+{p.gain_gpx_m:5.0f} m (GPX)  max {p.max_ele_gpx_m or float('nan'):5.0f} m  "
            f"points clean {len(p.clean):5d} used {len(p.used):5d}  route points {len(p.route_points):4d}"
            f"{'  (thinned to ~10 s)' if p.thinned else ''}"
        )
    for route_id in result.unchanged:
        print(f"{route_id:26s} unchanged (same file and method); use --force to reload")
    for route_id, path in result.missing.items():
        print(f"{route_id:26s} skipped: file not found at {path}")
    return 0


def _print_report(label: str, report) -> None:
    print(f"== {label}")
    print(f"   requests {report.requests}, rows written {report.rows_written}, new cells {report.cells_found}")
    if report.runs_fetched:
        print(f"   runs fetched: {len(report.runs_fetched)} ({report.runs_fetched[0]} .. {report.runs_fetched[-1]})")
    if report.runs_skipped_existing:
        print(f"   runs already stored (skipped): {len(report.runs_skipped_existing)}")
    if report.runs_unavailable:
        print(f"   runs not available: {', '.join(report.runs_unavailable)}")
    for note in report.notes:
        print(f"   note: {note}")
    for err in report.errors:
        print(f"   ERROR: {err}")


def cmd_weather_cells(args: argparse.Namespace) -> int:
    from .weather import collector, openmeteo

    conn = db.connect(args.db)
    report = collector.discover_cells(conn, openmeteo.http_fetcher(), Path(args.raw_dir))
    _print_report("cell discovery", report)
    for region, n in sorted(collector.cell_counts_by_region(conn).items()):
        print(f"   {region}: {n} unique HRDPS cells")
    return 0


def cmd_weather_collect(args: argparse.Namespace) -> int:
    from .weather import collector, openmeteo

    conn = db.connect(args.db)
    report = collector.collect_latest(conn, openmeteo.http_fetcher(), Path(args.raw_dir), region_ids=args.region)
    _print_report("collect latest run", report)
    return 1 if report.errors else 0


def cmd_weather_backfill(args: argparse.Namespace) -> int:
    from .weather import collector, openmeteo

    conn = db.connect(args.db)
    fetch = openmeteo.http_fetcher()
    run_hours = tuple(int(h) for h in args.run_hours.split(",")) if args.run_hours else ()
    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end or args.start)
        jobs = [collector.BackfillJob(f"{args.region or 'all'} {start}..{end}", args.region, start, end)]
    else:
        today = datetime.now(UTC).date()
        jobs = collector.plan_backfill(load_manifest(Path(args.manifest)), today)
    failed = False
    for job in jobs:
        report = collector.backfill(
            conn,
            fetch,
            job.start,
            job.end,
            region_ids=[job.region_id] if job.region_id else None,
            raw_dir=Path(args.raw_dir),
            run_hours=run_hours,
            include_runs=bool(run_hours),
            runs_from=job.runs_from,
        )
        _print_report(job.label, report)
        failed = failed or bool(report.errors)
    return 1 if failed else 0


def cmd_terrain_compute(args: argparse.Namespace) -> int:
    from .terrain.pipeline import route_terrain

    conn = db.connect(args.db)
    route_ids = args.route or [r[0] for r in conn.execute("SELECT route_id FROM routes ORDER BY route_id")]
    for route_id in route_ids:
        summary = route_terrain(conn, route_id)
        print(
            f"{route_id}: {summary['points']} route points, DEM window {summary['dem_shape']}, "
            f"{summary['points_outside_dem']} outside DEM, grid convergence {summary['convergence_deg_mean']:.1f} deg"
        )
    return 0


def cmd_exposure_run(args: argparse.Namespace) -> int:
    from .exposure import index as ex
    from .exposure import report as rp
    from .terrain import dem as demmod

    conn = db.connect(args.db)
    as_of = datetime.strptime(args.as_of, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    params = ex.ExposureParams(wind_level=args.wind_level, window_hours=args.window_hours)
    result = ex.route_exposure(conn, args.route, as_of, params, allow_stitched=not args.forecasts_only)
    ex.store_exposure(conn, result)
    stamp = as_of.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md = rp.render_markdown(conn, args.route, stamp)
    name = f"{args.route}_{as_of.strftime('%Y%m%dT%H%MZ')}"
    (out / f"{name}.md").write_text(md)
    dem_path = demmod.DEFAULT_DEM_DIR / f"{args.route}_mrdem30.tif"
    if dem_path.exists():
        rp.exposure_map(conn, args.route, stamp, dem_path, out / f"{name}.png")
    print(md)
    print(f"written to {out}/{name}.md")
    return 0


def cmd_obs_load(args: argparse.Namespace) -> int:
    from .observations.schema import load_file
    from .observations.store import store_observations

    conn = db.connect(args.db)
    total = 0
    for f in args.files:
        obs = load_file(Path(f))
        total += store_observations(conn, obs)
        print(f"{f}: {len(obs)} observations")
    n = conn.execute("SELECT COUNT(*), SUM(needs_review) FROM observations").fetchone()
    print(f"database now holds {n[0]} observations ({n[1] or 0} still need review)")
    return 0


def cmd_exposure_scan(args: argparse.Namespace) -> int:
    from .exposure import index as ex
    from .exposure.scan import scan

    conn = db.connect(args.db)
    rows = scan(
        conn, args.route, date.fromisoformat(args.start), date.fromisoformat(args.end), Path(args.out),
        hour_utc=args.hour, params=ex.ExposureParams(wind_level=args.wind_level),
    )
    active = [r for r in rows if r["m1_informative"]]
    print(f"{len(rows)} days scanned, {len(active)} with wind transport in M1; CSV: {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mountain", description="Mountain Software research pipeline")
    parser.add_argument("--db", default=str(db.DEFAULT_DB_PATH), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    routes = sub.add_parser("routes", help="route tracks and route points").add_subparsers(dest="action", required=True)
    load = routes.add_parser("load", help="load every track in the manifest into the database")
    load.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    load.add_argument("--force", action="store_true", help="reload even if unchanged (deletes downstream results)")
    load.set_defaults(func=cmd_routes_load)

    weather = sub.add_parser("weather", help="weather cells, collection and backfill").add_subparsers(
        dest="action", required=True
    )
    for name, func, text in (
        ("cells", cmd_weather_cells, "find the HRDPS grid cell of every route point"),
        ("collect", cmd_weather_collect, "store the newest model run for every cell (the future daily job)"),
        ("backfill", cmd_weather_backfill, "fill past dates from the archive"),
    ):
        p = weather.add_parser(name, help=text)
        p.add_argument("--raw-dir", default="data/raw")
        p.set_defaults(func=func)
        if name == "collect":
            p.add_argument("--region", action="append", help="limit to a region (repeatable)")
        if name == "backfill":
            p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
            p.add_argument("--region", help="region_id (with --start)")
            p.add_argument("--start", help="first day YYYY-MM-DD; without it the manifest plan is used")
            p.add_argument("--end", help="last day YYYY-MM-DD (default: --start)")
            p.add_argument(
                "--run-hours",
                default="0,12",
                help="UTC run hours to fetch as true forecasts, e.g. 0,6,12,18; empty string for stitched only",
            )

    terrain = sub.add_parser("terrain", help="DEM terrain features").add_subparsers(dest="action", required=True)
    tc = terrain.add_parser("compute", help="terrain features and Sx for route points (reads MRDEM-30)")
    tc.add_argument("--route", action="append", help="route_id (repeatable; default all loaded routes)")
    tc.set_defaults(func=cmd_terrain_compute)

    exposure = sub.add_parser("exposure", help="relative exposure to potential wind loading").add_subparsers(
        dest="action", required=True
    )
    er = exposure.add_parser("run", help="B0 and M1 for one route, window ending at --as-of")
    er.add_argument("--route", required=True)
    er.add_argument("--as-of", required=True, help="UTC time YYYY-MM-DDTHH:MM (end of the window)")
    er.add_argument("--window-hours", type=int, default=72)
    er.add_argument("--wind-level", choices=["blend", "700hPa", "hybrid", "10m"], default="blend")
    er.add_argument("--forecasts-only", action="store_true", help="never fall back to stitched archive values")
    er.add_argument("--out-dir", default="data/processed/reports")
    er.set_defaults(func=cmd_exposure_run)
    es = exposure.add_parser("scan", help="run B0/M1 once a day over a date range and write a CSV")
    es.add_argument("--route", required=True)
    es.add_argument("--start", required=True)
    es.add_argument("--end", required=True)
    es.add_argument("--hour", type=int, default=18, help="UTC hour the daily window ends (18 = noon MDT)")
    es.add_argument("--wind-level", choices=["blend", "700hPa", "hybrid", "10m"], default="blend")
    es.add_argument("--out", default="data/processed/reports/scan.csv")
    es.set_defaults(func=cmd_exposure_scan)

    obs = sub.add_parser("obs", help="field observations").add_subparsers(dest="action", required=True)
    ol = obs.add_parser("load", help="check and load observation TOML files")
    ol.add_argument("files", nargs="+")
    ol.set_defaults(func=cmd_obs_load)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
