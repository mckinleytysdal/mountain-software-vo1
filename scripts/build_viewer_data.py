"""Write data/processed/viewer.json: everything the viewer page shows.

    uv run python scripts/build_viewer_data.py [--research-db PATH] [--route north_victoria --as-of 2026-11-09T18:00:00Z]

Routes, terrain and observations come from the main database; weather
findings come from --research-db when the main database has no weather yet.
"""

import argparse
import json
from pathlib import Path

from mountain_software import db
from mountain_software.viewer import data as vd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-db", default="data/processed/mountain.sqlite")
    ap.add_argument("--research-db", default="data/processed/local_nv.sqlite")
    ap.add_argument("--route", default="north_victoria")
    ap.add_argument("--as-of", default="2026-11-09T18:00:00Z")
    ap.add_argument("--out", default="data/processed/viewer.json")
    a = ap.parse_args()
    main_db = db.connect(a.main_db)
    research = db.connect(a.research_db) if Path(a.research_db).exists() else main_db
    wx_main = vd.weather_summary(main_db)
    wx_source = main_db if any(w["rows"] for w in wx_main) else research
    out = {
        "status": vd.status_checks(main_db, wx_source),
        "routes": vd.routes_summary(main_db),
        "weather": vd.weather_summary(wx_source),
        "weather_db": str(Path(a.main_db if wx_source is main_db else a.research_db).name),
        "observations": vd.observations_summary(main_db),
        "station": vd.station_summary(wx_source),
        "scan": vd.scan_series(Path("data/processed/reports")),
        "exposure": {"route_id": a.route, "as_of": a.as_of, "points": vd.exposure_points(wx_source, a.route, a.as_of)},
        "window_weather": vd.window_weather(wx_source, a.route, a.as_of),
        "decisions": vd.decisions(),
    }
    Path(a.out).write_text(json.dumps(out, default=str))
    print(f"wrote {a.out}: {len(out['routes'])} routes, {len(out['exposure']['points'])} exposure points, "
          f"{len(out['decisions'])} decisions")


if __name__ == "__main__":
    main()
