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
    result = load_all(conn, Path(args.manifest))
    for route_id, p in result.loaded.items():
        print(
            f"{route_id:26s} raw {p.distance_raw_m / 1000:6.2f} km  used {p.distance_m / 1000:6.2f} km  "
            f"+{p.gain_gpx_m:5.0f} m (GPX)  max {p.max_ele_gpx_m or float('nan'):5.0f} m  "
            f"points clean {len(p.clean):5d} used {len(p.used):5d}  route points {len(p.route_points):4d}"
            f"{'  (thinned to ~10 s)' if p.thinned else ''}"
        )
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mountain", description="Mountain Software research pipeline")
    parser.add_argument("--db", default=str(db.DEFAULT_DB_PATH), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    routes = sub.add_parser("routes", help="route tracks and route points").add_subparsers(dest="action", required=True)
    load = routes.add_parser("load", help="load every track in the manifest into the database")
    load.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
