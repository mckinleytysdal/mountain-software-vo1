"""Command line entry point: ``uv run mountain <command>``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import db
from .routes import DEFAULT_MANIFEST, load_all


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mountain", description="Mountain Software research pipeline")
    parser.add_argument("--db", default=str(db.DEFAULT_DB_PATH), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    routes = sub.add_parser("routes", help="route tracks and route points").add_subparsers(dest="action", required=True)
    load = routes.add_parser("load", help="load every track in the manifest into the database")
    load.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    load.set_defaults(func=cmd_routes_load)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
