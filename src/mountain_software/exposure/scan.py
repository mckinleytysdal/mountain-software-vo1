"""Run B0 and M1 once a day over a date range, to find wind-transport events.

Each day's window ends at ``hour_utc`` (default 18 UTC = noon MDT). The scan
writes one CSV row per day: how much transport M1 saw, how much of the
weather came from the stitched archive, and how well B0 and M1 agree.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from . import index as ex

FIELDS = [
    "as_of_utc", "points", "hours_with_transport_max", "loading_sum", "scour_sum",
    "m1_informative", "b0_m1_rank_corr", "stitched_fraction", "data_age_hours",
]


def scan(
    conn: sqlite3.Connection,
    route_id: str,
    start: date,
    end: date,
    out_csv: Path,
    hour_utc: int = 18,
    params: ex.ExposureParams | None = None,
    store: bool = False,
) -> list[dict]:
    p = params or ex.ExposureParams()
    rows = []
    day = start
    while day <= end:
        as_of = datetime(day.year, day.month, day.day, hour_utc, tzinfo=UTC)
        res = ex.route_exposure(conn, route_id, as_of, p)
        if store:
            ex.store_exposure(conn, res)
        m1 = [r.m1_net for r in res.points]
        b0 = [r.b0_leeward_fraction for r in res.points]
        m1r, b0r = ex.relative_rank(m1), ex.relative_rank(b0)
        pairs = [(a, b) for a, b in zip(m1r, b0r) if a is not None and b is not None]
        corr = None
        if len(pairs) > 2:
            a, b = np.array(pairs).T
            if a.std() > 0 and b.std() > 0:
                corr = float(np.corrcoef(a, b)[0, 1])
        rows.append(
            {
                "as_of_utc": as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "points": len(res.points),
                "hours_with_transport_max": max((r.hours_used for r in res.points), default=0),
                "loading_sum": round(sum(r.m1_loading for r in res.points), 3),
                "scour_sum": round(sum(r.m1_scour for r in res.points), 3),
                "m1_informative": any(v is not None for v in m1r),
                "b0_m1_rank_corr": None if corr is None else round(corr, 3),
                "stitched_fraction": round(res.stitched_fraction, 3),
                "data_age_hours": None if res.data_age_hours is None else round(res.data_age_hours, 1),
            }
        )
        day += timedelta(days=1)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return rows
