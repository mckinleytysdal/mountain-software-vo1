"""Mountain Software: local viewer and control panel.

Run from the repository folder:

    uv sync --group app
    uv run streamlit run app/streamlit_app.py

It reads your own database (data/processed/mountain.sqlite by default), shows
where the project stands and why, and has buttons that run each pipeline
step. Every number on screen comes straight from the database or docs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mountain_software import db  # noqa: E402
from mountain_software.exposure import index as ex  # noqa: E402
from mountain_software.viewer import data as vd  # noqa: E402

AVCAN = "https://avalanche.ca/forecasts"
LABEL = "relative exposure to potential wind loading"
# Colour ramp for the index: white to purple-blue, chosen so it does not look
# like the avalanche danger scale.
RAMP = ["#e4e9f2", "#3a3283"]

st.set_page_config(page_title="Mountain Software", page_icon="⛰", layout="wide")


@st.cache_resource
def connect(path: str):
    return db.connect(path)


def pick_db() -> tuple[str, object]:
    default = str(ROOT / "data/processed/mountain.sqlite")
    path = st.sidebar.text_input("Database", value=default, key="db_path")
    if not Path(path).exists():
        st.sidebar.warning("No database yet. Use Run pipeline > Load routes.")
    return path, connect(path)


def footer() -> None:
    st.caption(
        f"Exploratory research output: not a hazard rating, not an official warning, not a verified observation. "
        f"Official forecasts: {AVCAN}. Weather by Open-Meteo.com (CC BY 4.0), GEM HRDPS (ECCC). "
        "DEM: NRCan MRDEM-30 (OGL-Canada 2.0), contains modified Copernicus GLO-30 data."
    )


# ------------------------------------------------------------------ pages


def page_status(conn) -> None:
    st.header("Where we are")
    checks = vd.status_checks(conn)
    icon = {"done": "✅", "partial": "🔄", "blocked": "⏸"}
    for c in checks:
        st.markdown(f"{icon[c['state']]} **{c['item']}** · {c['detail']}")
    st.subheader("Weather stored")
    wx = vd.weather_summary(conn)
    st.dataframe(pd.DataFrame(wx) if wx else pd.DataFrame([{"note": "no weather yet: run Weather cells and Backfill"}]), hide_index=True)
    obs = vd.observations_summary(conn)
    st.metric("Labelled observations (loaded / scoured / none seen)", obs["labelled"], help="The research test needs about 10 to start.")


def page_findings(conn) -> None:
    st.header("What I think and why")
    st.write("Each result below is recomputed from the database. Exploratory, with the uncertainty stated.")
    stats = vd.station_summary(conn)
    if stats:
        st.subheader("Model wind vs Bosworth Upper ridge-top station")
        st.caption(stats[0]["cell_note"])
        df = pd.DataFrame([{k: s[k] for k in ("variable", "model_variable", "n", "bias", "mae", "corr", "station_mean", "model_mean")} for s in stats])
        st.dataframe(df.round(2), hide_index=True)
        st.write("Reading: 10 m model wind far below measured ridge wind means the index must use ridge-height (700 hPa) wind, mixed by height.")
    else:
        st.info("No station data in this database yet. See docs/stations.md for the recorded result.")
    scans = vd.scan_series(ROOT / "data/processed/reports")
    if scans:
        st.subheader("Potential loading per day (72 h windows)")
        rows = [{"day": r["day"], "wind": k, "loading": r["loading"]} for k, v in scans.items() for r in v]
        chart = alt.Chart(pd.DataFrame(rows)).mark_line().encode(x="day:T", y="loading:Q", color="wind:N")
        st.altair_chart(chart, width="stretch")
    st.subheader("Documents")
    for doc in ("docs/research-log/2026-11-18-terrain-exposure-observations.md", "docs/stations.md", "docs/literature.md"):
        with st.expander(doc):
            st.markdown((ROOT / doc).read_text())


def page_explore(conn) -> None:
    st.header("Explore a route")
    routes = [r["route_id"] for r in vd.routes_summary(conn)]
    if not routes:
        st.info("No routes loaded yet.")
        return
    c1, c2, c3 = st.columns(3)
    route = c1.selectbox("Route", routes, index=routes.index("north_victoria") if "north_victoria" in routes else 0)
    day = c2.date_input("Window ends (UTC date)", value=datetime(2026, 11, 9).date())
    hour = c3.number_input("at UTC hour", 0, 23, 18)
    with st.expander("Settings (each one is recorded with the result)"):
        a, b, c = st.columns(3)
        wind = a.selectbox("Wind that drives transport", ["blend", "700hPa", "hybrid", "10m"])
        thr = b.slider("Transport threshold (km/h)", 10, 50, 25)
        dmax = c.selectbox("Upwind search distance (m)", [300.0, 100.0])
    as_of = datetime(day.year, day.month, day.day, int(hour), tzinfo=UTC)
    try:
        res = ex.route_exposure(conn, route, as_of, ex.ExposureParams(wind_level=wind, transport_threshold_kmh=thr, sx_dmax_m=dmax))
    except ValueError as exc:
        st.warning(f"Cannot score this route yet: {exc}")
        return
    ranks = ex.relative_rank([p.m1_net for p in res.points])
    pts = pd.DataFrame(vd.exposure_points(conn, route, "none"))
    pts["index"] = ranks
    pts["loading"] = [p.m1_loading for p in res.points]
    pts["scour"] = [p.m1_scour for p in res.points]
    pts["b0_leeward_fraction"] = [p.b0_leeward_fraction for p in res.points]
    st.caption(f"Data age at window end: {res.data_age_hours:.0f} h · stitched-archive share {res.stitched_fraction:.0%}"
               if res.data_age_hours is not None else "No weather in this window.")
    if pts["index"].isna().all():
        st.warning("No result for this window: no hour had wind above the threshold with snow available, so points cannot be ranked.")
    wx = pd.DataFrame(vd.window_weather(conn, route, as_of.strftime("%Y-%m-%dT%H:%M:%SZ")))
    if not wx.empty:
        st.subheader("What the model said in the window")
        st.dataframe(wx, hide_index=True)
    left, right = st.columns([3, 2])
    scale = alt.Scale(domain=[0, 1], range=RAMP)
    base = alt.Chart(pts).encode(
        x=alt.X("lon:Q", scale=alt.Scale(zero=False), title=None), y=alt.Y("lat:Q", scale=alt.Scale(zero=False), title=None),
        tooltip=["km", "elev_m", "landform_class", "aspect", "slope", "index", "loading", "scour", "b0_leeward_fraction"],
    )
    left.altair_chart(base.mark_circle(size=90, stroke="#17212b", strokeWidth=0.5).encode(color=alt.Color("index:Q", scale=scale, title=LABEL)), width="stretch")
    right.altair_chart(
        alt.Chart(pts).mark_bar().encode(x="km:Q", y=alt.Y("index:Q", title=LABEL), color=alt.Color("index:Q", scale=scale, legend=None)),
        width="stretch",
    )
    st.subheader("Why each point got its score")
    st.write("Score = sum over the window of (wind above threshold, to the 4th power) × (snow available) × (shelter from the terrain upwind), then ranked within the route. Loading comes from sheltered hours, scour from exposed hours.")
    st.dataframe(pts[["km", "elev_m", "landform_class", "aspect", "slope", "loading", "scour", "index", "b0_leeward_fraction"]].round(2), hide_index=True)
    if st.button("Save this result to the database"):
        n = ex.store_exposure(conn, res)
        st.success(f"Saved {n} rows (B0 and M1) for {as_of:%Y-%m-%d %H:%M} UTC.")


def page_decisions(conn) -> None:
    st.header("Every decision, with the reason")
    q = st.text_input("Search", key="dec_q")
    for d in vd.decisions():
        if q and q.lower() not in (d["id"] + d["title"] + d["text"]).lower():
            continue
        with st.expander(f"{d['id']} · {d['title']}"):
            st.caption(d["section"])
            st.markdown(d["text"])


STEPS = [
    ("Load routes", ["routes", "load"]),
    ("Weather cells", ["weather", "cells"]),
    ("Backfill weather (manifest plan)", ["weather", "backfill"]),
    ("Collect newest model run", ["weather", "collect"]),
    ("Terrain features", ["terrain", "compute"]),
    ("Run tests", None),
]


def run_cmd(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)[-6000:]


def page_run(db_path: str) -> None:
    st.header("Run pipeline")
    st.write("Each button runs one step and shows its output. Every step is safe to repeat: it adds no duplicate rows.")
    for label, cmd in STEPS:
        if st.button(label, key=f"run_{label}"):
            args = [sys.executable, "-m", "pytest", "-q"] if cmd is None else [sys.executable, "-m", "mountain_software.cli", "--db", db_path, *cmd]
            with st.spinner(f"Running {label}…"):
                code, out = run_cmd(args)
            (st.success if code == 0 else st.error)(f"{label}: exit code {code}")
            st.code(out or "(no output)")
    st.caption("The weather API's free tier has a daily limit; if it is reached, the step says so and a rerun later continues where it stopped.")


def main() -> None:
    st.title("Mountain Software")
    db_path, conn = pick_db()
    page = st.sidebar.radio("Page", ["Where we are", "What I think and why", "Explore a route", "Every decision", "Run pipeline"])
    {
        "Where we are": lambda: page_status(conn),
        "What I think and why": lambda: page_findings(conn),
        "Explore a route": lambda: page_explore(conn),
        "Every decision": lambda: page_decisions(conn),
        "Run pipeline": lambda: page_run(db_path),
    }[page]()
    footer()


main()
