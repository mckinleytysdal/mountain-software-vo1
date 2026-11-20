"""Build docs/mountain-software-overview.pdf (project overview for a coordinator)."""

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

REPO = Path(sys.argv[1])
OUT = Path(sys.argv[2])
IMG_LANDFORM = Path(sys.argv[3])
IMG_EXPOSURE = Path(sys.argv[4])

F = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Body", F + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("Body-Bold", F + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "DejaVuSansMono.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily  # noqa: E402

registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold")

INK = colors.HexColor("#17212b")
MUTED = colors.HexColor("#5a6875")
LINE = colors.HexColor("#d8e0e5")
ICE = colors.HexColor("#2c6a8a")
ICE_SOFT = colors.HexColor("#e6f0f5")
VIOLET = colors.HexColor("#4a3d8f")

S = {
    "title": ParagraphStyle("title", fontName="Body-Bold", fontSize=22, leading=27, textColor=INK, spaceAfter=6),
    "sub": ParagraphStyle("sub", fontName="Body", fontSize=10.5, leading=15, textColor=MUTED, spaceAfter=14),
    "h1": ParagraphStyle("h1", fontName="Body-Bold", fontSize=15, leading=19, textColor=INK, spaceBefore=16, spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Body-Bold", fontSize=11.5, leading=15, textColor=ICE, spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "p": ParagraphStyle("p", fontName="Body", fontSize=9.5, leading=13.5, textColor=INK, spaceAfter=5, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="Body", fontSize=8, leading=11, textColor=MUTED, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.3, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Body-Bold", fontSize=8.3, leading=11, textColor=INK),
    "bullet": ParagraphStyle("bullet", fontName="Body", fontSize=9.5, leading=13.5, textColor=INK, leftIndent=12, bulletIndent=2, spaceAfter=2),
}


def P(t, s="p"):
    return Paragraph(t, S[s])


def bullets(items):
    return [Paragraph(t, S["bullet"], bulletText="•") for t in items]


def table(rows, widths, header=True, hl_rows=()):
    data = [[Paragraph(str(c), S["cellb"] if (header and i == 0) else S["cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), ICE_SOFT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, ICE)]
    for r in hl_rows:
        style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f1eefa")))
    t.setStyle(TableStyle(style))
    return t


W = 7.0 * inch


def footer(c, doc):
    c.saveState()
    c.setFont("Body", 7.5)
    c.setFillColor(MUTED)
    c.drawString(0.75 * inch, 0.5 * inch, "Mountain Software · project overview · 20 Nov 2026 · exploratory research, not a hazard rating or official warning")
    c.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    c.restoreState()


story = []
story += [
    P("Mountain Software", "title"),
    P("Project overview: every module, what is complete, what was brainstormed, and what comes next. "
      "Prepared 20 November 2026 for McKinley Tysdal. Repository mckinleytysdal/mountain-software-vo1, branch "
      "claude/friendly-galileo-6jgqu5 (draft pull request #1, automated tests passing).", "sub"),
    P("The question", "h1"),
    P("Does combining weather history, terrain from an elevation model (DEM), and dated human observations explain where "
      "wind <b>loads</b> snow and where it <b>scours</b> it on Canadian Rockies peaks better than the simple rule "
      "\"the slope facing away from the wind collects snow\"? The project is evidence synthesis and research. "
      "It never produces safe/unsafe or go/no-go verdicts; its output is called <b>relative exposure to potential wind "
      "loading</b>, always shown with evidence, data age, uncertainty and a link to the official Avalanche Canada forecast."),
    P("Study areas: three weather regimes. Columbia Icefield (Silverhorn route on Mount Athabasca), Lake Louise "
      "(McKinley's own North Victoria climb, 16 Oct 2026), and Burstall (Mount Sir Douglas West Ridge plus the "
      "French-Haig-Robertson ski traverse)."),
    P("At a glance", "h1"),
    table([
        ["Area", "State"],
        ["Pipeline (5 modules)", "Built and tested: 142 automated tests, no network needed; continuous integration on GitHub"],
        ["Routes", "All 4 real tracks loaded; hand-checked distances reproduced"],
        ["Weather", "16 real model cells; 30 / 30 / 90 days of forecasts stored for Icefield / Burstall / Lake Louise"],
        ["Terrain", "Slope, aspect, landform class and wind shelter for all 287 route points"],
        ["Exposure index", "Runs on every route; North Victoria explored in depth"],
        ["Model check", "Compared with 3 real mountain weather stations over 90 days"],
        ["Research answer", "<b>Not yet possible</b>: needs field observations labelled \"loaded\" or \"scoured\" (0 so far)"],
    ], [1.6 * inch, 5.4 * inch]),
    Spacer(1, 6),
    P("The pipeline in one line: GPX track → route points every 250 m → each point's weather-model cell and hourly weather "
      "→ each point's terrain from a 30 m elevation map → a ranked index of where blown snow would collect → checked "
      "against field observations.", "small"),
]

# ---------------- Module 1
story += [
    P("Module 1: Route points (complete)", "h1"),
    P("Turns each GPX file into clean, evenly spaced route points stored in a SQLite database."),
    table([
        ["Step", "What happens"],
        ["Read", "Parses GPX 1.0 and 1.1 with Python's built-in XML reader: track points, route points, waypoints, copyright and licence tags."],
        ["Clean", "Drops impossible coordinates (for example 0,0) and back-to-back repeats of the same spot."],
        ["Thin", "Watch tracks recorded every second wobble a few metres per fix, which inflates distance (33.0 km instead of about 25 km). "
                 "Timed 1 Hz tracks are thinned to about one point per 10 seconds."],
        ["Measure", "Distance on a sphere; elevation gain that ignores wiggles under 3 m."],
        ["Sample", "One route point every 250 m along the track (along the bends, not straight-line)."],
        ["Store", "Regions, peaks, routes, route points and a source record per track (source, download date, terms, file fingerprint). "
                  "Reloading an unchanged file is skipped so downstream results are kept."],
    ], [1.0 * inch, 6.0 * inch]),
    Spacer(1, 6),
    P("Data handling: a committed manifest lists every track. Only McKinley's own North Victoria track is in the public "
      "repository; the CalTopo, TrailAmigo and AllTrails tracks stay local (the Sir Douglas file carries a copyright notice)."),
    table([
        ["Track", "Hand-checked target", "Pipeline result", "Status"],
        ["North Victoria (own, Strava)", "33.0 km raw, 24.97 km thinned", "32.99 / 24.96 km, +1,843 m, 101 points", "pass"],
        ["Silverhorn (CalTopo)", "10.49 km, +1,598 m, 1,403 points", "10.52 km, +1,598 m, 44 points", "pass (point count not reproducible)"],
        ["Sir Douglas West Ridge (TrailAmigo)", "13.99 km, 814 points", "13.99 km, 57 points", "pass"],
        ["French-Haig-Robertson (AllTrails)", "20.91 km, 3,953 points", "20.91 km, 85 points", "pass"],
    ], [1.9 * inch, 1.7 * inch, 2.1 * inch, 1.3 * inch]),
]

# ---------------- Module 2
story += [
    P("Module 2: Weather collector and backfill (complete)", "h1"),
    P("Finds the weather-model grid cell for every route point and stores hourly model weather, keeping the time a "
      "forecast was <b>made</b> (issue time) separate from the time it is <b>about</b> (valid time) to prevent look-ahead bias."),
    *bullets([
        "Model: GEM HRDPS (Environment and Climate Change Canada, 2.5 km grid, 48-hour runs at 00, 06, 12, 18 UTC) via Open-Meteo.",
        "Real grid cells, read from the coordinates the API returns: Icefield 2, Lake Louise 5, Burstall 9 (Sir Douglas 6 and FHR 7 share 4); 16 in total. Each is fetched once.",
        "Ten variables: temperature, 10 m wind speed, direction and gusts, snowfall, precipitation, and 700 hPa (about 3,000 m, ridge-top height) wind speed, direction, height and temperature.",
    ]),
    table([
        ["Product", "What it gives", "Issue time known?", "Archive starts"],
        ["Single runs", "One model run: a true forecast", "Yes", "2 Apr 2026"],
        ["Historical (stitched)", "First hours of every run joined together", "No: never called a forecast", "3 Mar 2023"],
        ["Forecast API", "Used only to find each point's cell", "n/a", "n/a"],
    ], [1.4 * inch, 2.4 * inch, 1.8 * inch, 1.4 * inch]),
    Spacer(1, 6),
    *bullets([
        "Safeguards: units checked on every response; duplicate hours, bad timestamps and missing values detected; every raw response saved (kept out of git); reruns add no duplicate rows; the database refuses a stitched value that claims an issue time.",
        "Backfill completed: Icefield 30 days (59 runs), Burstall 30 days (59 runs), Lake Louise 90 days (179 runs). North Victoria trip day has true forecasts; Silverhorn's 2025 date predates the archive, so only stitched values exist.",
        "Daily collector: built and tested but deliberately not scheduled until the Mini PC exists.",
    ]),
]

# ---------------- Module 3
story += [
    P("Module 3: Terrain from a DEM (complete)", "h1"),
    P("Describes the ground at every route point from NRCan MRDEM-30, a 30 m bare-earth elevation model covering all of "
      "Canada (Open Government Licence, includes modified Copernicus data)."),
    table([
        ["Feature", "Meaning"],
        ["DEM elevation", "Ground height; used instead of GPS elevation for all terrain work"],
        ["Slope and aspect", "Steepness and the direction the slope faces, corrected from map grid north to true north (about 19° difference here)"],
        ["Curvature", "Bump (convex) or hollow (concave)"],
        ["Topographic position (150 m and 1,000 m)", "Higher or lower than the surrounding ground"],
        ["Landform class", "Ridge, couloir/gully, basin/valley, steep face or open slope (rule-based)"],
        ["Wind shelter (Sx)", "Maximum upwind slope (Winstral et al. 2002) for 36 wind directions: positive = sheltered by higher ground upwind, negative = exposed"],
    ], [2.0 * inch, 5.0 * inch]),
    Spacer(1, 6),
    P("Not yet classified: surface type (glacier, rock, snow). It needs glacier outlines and satellite imagery."),
]
if IMG_LANDFORM.exists():
    story += [KeepTogether([Image(str(IMG_LANDFORM), width=5.6 * inch, height=5.6 * inch * 0.798),
                            P("North Victoria: rule-based landform classes from the 30 m DEM, with the route. Exploratory; not a hazard map.", "small")])]

# ---------------- Module 4
story += [
    P("Module 4: Exposure index (complete; not yet tested against reality)", "h1"),
    P("Ranks route points by <b>relative exposure to potential wind loading</b> over a 72-hour window."),
    *bullets([
        "<b>B0 (baseline):</b> a slope counts as leeward when it faces within 45° of the downwind direction.",
        "<b>M1 (terrain index):</b> for every hour, wind strength above 25 km/h (to the 4th power, after Pomeroy) × available fresh snow × shelter from the terrain upwind (Sx). Sheltered hours add loading, exposed hours add scour. Summed over 72 hours and ranked within the route from 0 to 1.",
        "<b>Wind used:</b> a blend of 10 m and ridge-height (700 hPa) wind, weighted by how far each point rises above the model's ground (version 5).",
        "<b>No look-ahead:</b> each hour uses only model runs published by the end of the window (3 hours after run time).",
        "<b>Reports</b> always show evidence, data age, uncertainty and the Avalanche Canada link, and say \"no result\" when nothing could be ranked.",
        "<b>Scan tool:</b> runs the index once a day over a date range to find storm windows.",
    ]),
]
if IMG_EXPOSURE.exists():
    story += [KeepTogether([Image(str(IMG_EXPOSURE), width=5.6 * inch, height=5.6 * inch * 0.679),
                            P("North Victoria, 72 hours ending 9 Nov 2026 18:00 UTC. Darker = higher relative exposure to potential wind loading "
                              "(a rank within this route, not a hazard rating). The upper NE ridge ranks highest, the lee of that storm's WSW wind.", "small")])]

# ---------------- Module 5
story += [
    P("Module 5: Field observations (complete; no labelled data yet)", "h1"),
    *bullets([
        "Template (templates/field_observation.toml): labelled fields plus one plain sentence: time, GPS, elevation, forecast carried, wind, temperature, snow surface, wind-transport signs, avalanches, glacier notes, photos. Negatives are logged too.",
        "The key label is <b>wind_effect</b>: loaded, scoured, mixed, none_seen or unknown.",
        "Checker: times need a time zone; observed and published times are separate; a forecast issued after the observation is refused; another person's report must carry a link, never a copy.",
        "Each observation links to the nearest route point within 300 m.",
        "77 draft entries were extracted word-for-word from McKinley's six trip reports (eight summits). None states that snow was loaded or scoured, so none can serve as a test label.",
    ]),
]

# ---------------- Extras
story += [
    P("Supporting work", "h1"),
    table([
        ["Piece", "What it does"],
        ["Station check", "Compares model wind and temperature with three Avalanche Canada / Parks Canada stations, each against its own model cell, over 90 days. Only summary statistics are published (data terms)."],
        ["Status web page", "Private page with the checklist, each finding with its evidence, a clickable North Victoria storm explaining every point's score, routes, and all 47 decisions."],
        ["Local app", "Streamlit app (uv run streamlit run app/streamlit_app.py): live views, route explorer with adjustable settings, and buttons that run each pipeline step."],
        ["Documentation", "Decision log (D1-D47 with reasons), weather-data notes, station results, literature sources, research log, status against the spec."],
        ["Quality", "142 tests; GitHub continuous integration; an independent code review found two look-ahead bugs, both fixed with regression tests."],
    ], [1.4 * inch, 5.6 * inch]),
]

# ---------------- Findings
story += [
    P("Findings so far (exploratory)", "h1"),
    table([
        ["Station (height; model ground)", "10 m model wind error", "700 hPa error", "Blended error", "Notes"],
        ["Bosworth Upper (2,745 m; 1,965 m)", "16.7 km/h", "10.1", "<b>6.5</b>", "10 m wind never reached 25 km/h; station did for 921 h"],
        ["Tangle Ridge (3,009 m; 2,157 m)", "16.5", "10.8", "<b>10.0</b>", "10 m never reached 25 km/h; station did for 643 h"],
        ["Burstall Pass (2,300 m; 2,348 m)", "4.2", "27.9", "<b>4.2</b>", "Sheltered pass; blend falls back to 10 m wind by itself"],
    ], [1.9 * inch, 1.2 * inch, 0.9 * inch, 0.9 * inch, 2.1 * inch], hl_rows=()),
    P("Typical error = mean absolute error, 20 Aug - 17 Nov 2026, about 2,160 hours per station.", "small"),
    *bullets([
        "<b>1. The model's 10 m wind badly under-reads ridge wind.</b> Its ground sits 800+ m below the ridges, so its \"10 m wind\" is valley wind.",
        "<b>2. Blending 10 m and ridge-height wind by height is best</b> at all three stations, and stops valley points getting ridge-top wind.",
        "<b>3. The wind source dominates the result.</b> Changing the shelter search distance, threshold or exponent keeps the ranking (correlation 0.86-1.00); changing the wind source changes it (0.18-0.35).",
        "<b>4. The same storms drive all regions:</b> 8-9 and 12-13 November, ridge-height wind 75-88 km/h from SW to WSW. How much a route \"sees\" depends on how far its points rise above the model ground (Silverhorn most, Burstall routes least).",
        "<b>5. North Victoria, 9 November:</b> the upper NE ridge just below the summit ranks highest, the lee of a WSW wind.",
        "<b>6. M1 ranks points differently from B0</b> (median rank correlation 0.08-0.37 by route). Whether it is better is untested.",
    ]),
    P("Approaches that failed and were replaced (kept on record on purpose)", "h2"),
    *bullets([
        "M1 driven by 10 m wind: saw no snow transport on any day.",
        "Ridge-height wind alone: ranked valley gullies by Lake Louise highest.",
        "Landform rules v1: painted whole upper mountains as \"ridge\".",
        "\"Use 10 m wind direction\": looked better at one station on a provisional cell, did not hold on the real cells.",
    ]),
]

# ---------------- Status vs spec
story += [
    P("Status against the Prototype 0 specification", "h1"),
    table([
        ["Check", "Status"],
        ["Repo runs from a clean checkout; tests pass", "Done"],
        ["Every track has a source record; no third-party GPX in git", "Done"],
        ["Hand-checked route numbers reproduced", "Done (one point count not reproducible, documented)"],
        ["Each weather cell fetched once; issue and valid time separate; raw responses kept; no duplicates on rerun", "Done"],
        ["Backfill 30 / 30 / 90 days plus the two trip dates; issue-time limits documented", "Done"],
        ["Daily schedule not switched on", "Done (waits for the Mini PC)"],
        ["One peak's terrain classes and exposure index, reproducible", "Done (North Victoria; all routes computed)"],
        ["At least 10 field observations", "<b>Waiting</b>: 77 stored, 0 with a wind-effect label"],
        ["Test whether M1 beats B0", "<b>Waiting</b> on those labels"],
    ], [4.6 * inch, 2.4 * inch]),
]

# ---------------- Brainstormed
story += [
    P("Brainstormed, not built", "h1"),
    *bullets([
        "More label sources: Avalanche Canada field reports (link and facts only), Sentinel-2 satellite images of scoured versus loaded slopes after storms, radar (SAR) imagery, avalog.co observations along the FHR traverse (terms to check).",
        "Glacier outlines from RGI 7.0 (CC BY 4.0) to fill the surface class; satellite snow cover for rock versus snow.",
        "Finer elevation data: NRCan 1-2 m lidar (HRDEM) where it exists (likely BC side only).",
        "Winstral's drift-separator parameter; a temperature-dependent transport threshold (Li and Pomeroy 1997).",
        "Strong-wind effect: above about 40 km/h snow spreads widely or sublimates instead of loading lee slopes; M1 ignores this.",
        "Forecast-error study with the Previous Runs API (1-7 day lead times).",
        "Longer station records (ECCC Yoho Park, Nakiska Ridgetop) and per-station wind corrections (the blend reads about 7 km/h high at Tangle Ridge).",
    ]),
]

# ---------------- Next
story += [
    P("What comes next", "h1"),
    P("Near term", "h2"),
    *bullets([
        "About 10 labelled field observations: one line per notable slope with time and place, saying whether wind <b>added</b> snow (pillowy, slab, fresh cornice) or <b>stripped</b> it (hard, rippled, rock showing). Storms like 8-9 November are the best moments.",
        "Evaluation code: compare B0 and M1 against those labels, splitting by date and holding out whole regions as the specification requires.",
        "Teaching and quiz sessions for each module, on request.",
    ]),
    P("Prototype 1", "h2"),
    *bullets([
        "M2: learned weights from labelled observations.",
        "Satellite-based labels; glacier and surface classes.",
        "Daily collector running on the Mini PC; more stations; mountain-wide grids beyond route points.",
    ]),
    P("Long term", "h2"),
    P("A trained agent that explains conditions per peak on a website, keeping the wording rules. Realistic only after a "
      "season or more of labelled observations."),
    P("What is needed from McKinley", "h1"),
    *bullets([
        "Field observations with a wind-effect label. This is the only real blocker.",
        "Say \"teach me Module X\" whenever a learning session is wanted.",
    ]),
    Spacer(1, 10),
    P("Data credits: weather by Open-Meteo.com (CC BY 4.0) from Environment and Climate Change Canada's HRDPS; elevation from "
      "NRCan MRDEM-30 (Open Government Licence - Canada 2.0), containing modified Copernicus GLO-30 data; station statistics "
      "derived from Avalanche Canada / Parks Canada / Kananaskis Country data. Official avalanche forecasts: avalanche.ca/forecasts.", "small"),
]

doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.8 * inch, title="Mountain Software: project overview",
                        author="McKinley Tysdal", subject="Wind loading research: modules, status, findings, plans")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("wrote", OUT)
