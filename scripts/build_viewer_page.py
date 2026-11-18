"""Fill the viewer page template with data/processed/viewer.json.

    uv run python scripts/build_viewer_data.py
    uv run python scripts/build_viewer_page.py   # writes data/processed/viewer.html
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

TEMPLATE = Path("src/mountain_software/viewer/page_template.html")

# Recorded result (docs/stations.md): height-blended wind vs Bosworth Upper,
# 2026-08-20 to 2026-11-17, 2,160 hours, provisional nearest-cell values.
BLEND_STATION = {"model_mean": 20.8, "bias": -3.6, "mae": 7.2, "corr": 0.79}


def main() -> None:
    data = json.loads(Path("data/processed/viewer.json").read_text())
    as_of = datetime.strptime(data["exposure"]["as_of"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    data["exposure"]["window_start"] = (as_of - timedelta(hours=72)).strftime("%d %b %H:%M")
    data["exposure"]["as_of"] = as_of.strftime("%d %b %Y %H:%M")
    data["built"] = datetime.now(UTC).strftime("updated %d %b %Y")
    data["blend_station"] = BLEND_STATION
    # Only McKinley's own track geometry is shown on the page.
    blob = json.dumps(data, default=str).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("__DATA__", blob)
    out = Path("data/processed/viewer.html")
    out.write_text(html)
    print(f"wrote {out} ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
