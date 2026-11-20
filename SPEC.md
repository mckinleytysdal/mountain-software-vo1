# Mountain Software: Project Spec v1 and Prototype 0 Plan

Draft date: 2026-11-18 (v0 drafted 2026-11-17; route files received and checked that day). Status: planning only. Nothing here has been built or validated.
Sources: the ChatGPT brainstorming chat, the project description, and two decision interviews in Claude chats.

## 1. Purpose

Mountain Software is a resume and research project. It investigates whether combining weather history, terrain, and dated human observations explains where wind loads snow and where wind scours it on Canadian Rockies peaks, better than a simple aspect-versus-wind-direction rule.

It is evidence synthesis and research, not a source of go/no-go decisions.

Long-term vision (not part of Prototype 0): a trained agent that interprets this data and explains conditions per peak on a website. That only becomes realistic after the data foundation, the exposure index, and enough labelled observations exist.

## 2. Decisions made

| Topic | Decision |
|---|---|
| Deliverables of the planning rounds | Project spec, Prototype 0 plan, a repo-level CLAUDE.md, and the first Claude Code prompt |
| Regions | Three weather regimes: Columbia Icefield (Athabasca), Lake Louise (North Victoria), and Burstall (Mount Sir Douglas and the French-Haig-Robertson line, treated as one area with different mountain features and elevation ranges). Mixed 11,000ers and easy testbed peaks are allowed. |
| Routes | Athabasca: Silverhorn. Lake Louise: North Victoria (own 2026-10-16 Strava activity). Burstall: Sir Douglas West Ridge, plus the French-Haig-Robertson (FHR) ski traverse as a second terrain transect. |
| First prediction target | Wind loading versus scour and snow accumulation by terrain feature (lee versus windward slopes, pockets, couloirs, ridges, glaciers, basins and valleys, rock versus snow surface) |
| Terrain in Prototype 0 | Included: DEM terrain features and a first exposure index |
| Label sources | Own field observations, Avalanche Canada MIN public reports, Sentinel-2 and SAR satellite imagery, own and other people's trip photos |
| Field capture | Structured written template, each entry stored as labelled fields plus a plain sentence |
| Collector host | Planned Mini PC. The collector is built and tested now, but the daily run waits for the Mini PC. Until then, past data comes from archive backfill. |
| Prototype 0 done | Pipeline plus a first exposure index |
| First Claude Code job | Module 1 (route points from GPX) and Module 2 (weather collector with backfill), with a stop between them |
| Build and learning rule | Claude Code drafts each module with tests, then teaches it in easy words with analogies, then quizzes McKinley. The next module starts only after McKinley passes the quiz. |
| Teaching level | Beginner-friendly, with climbing and weather analogies. Every new term is defined once. |
| Repo visibility | Public. McKinley's own North Victoria Strava track is committed. All third-party tracks are git-ignored. A manifest records source, download date, and terms note. |
| Python setup | `uv` with `pyproject.toml`, SQLite, `pytest` |
| Backfill windows | 30 days for Icefield, 30 days for Burstall, 90 days for the Lake Louise group, plus two single dates: Silverhorn 2025-06-27 and North Victoria 2026-10-16 |
| Output wording | Evidence and uncertainty text plus a relative exposure index, never a safe/unsafe verdict |
| Process | Planning happens in chat; building happens in Claude Code |

## 3. Research question and hypotheses

Question: does a terrain-informed wind exposure index, driven by forecast wind and a DEM, separate loaded terrain from scoured terrain better than an aspect-only baseline?

- Baseline B0: a slope is "leeward" if its aspect faces away from the forecast wind direction within a fixed angle. Wind direction is circular, so 359 degrees and 1 degree are treated as nearly equal.
- Model M1: exposure index from wind direction, wind speed, snowfall, and upwind terrain shelter or exposure computed from the DEM (Sx-style measures, to be confirmed in the literature).
- Later: M2 adds prior observations and learned weights.
- Evaluation: chronological splits, and hold out an entire region (Icefield, Lake Louise, or Burstall). Routes in the same region share weather cells, so they are never split across training and test data. Sir Douglas and FHR always travel together.
- Expect few labels in the first season. Report results as exploratory with uncertainty, and document failed hypotheses.

## 4. Data sources and grids

Keep two separate grids and join them.

Weather grid (model cells):
- GEM HRDPS Continental through Open-Meteo: 2.5 km, hourly, 2-day forecasts, updated every 6 hours. Archived forecasts available from 2023-03-03.
- GEM RDPS Regional: 10 km, archived from 2022-11-23.
- ERA5-Land reanalysis: about 9 km, from 1950, used as a baseline and long history, not as truth.
- Previous Runs API: fixed lead-time offsets of 1 to 7 days, for forecast-error work.
- Always store forecast issue time and valid time separately, to prevent look-ahead bias. For archived data, check what the API actually provides about issue time and record that honestly. Do not label a value as a true forecast if the API cannot say when it was issued.
- Fetch each unique model cell once and store a `cell_id`. A rough bounding-box estimate suggests 2 to 4 cells for Athabasca and 3 to 6 for each Burstall route, with heavy overlap between the two Burstall routes. The real count must come from the grid coordinates the API returns.
- First variables to store: temperature, wind speed, wind direction, wind gusts, snowfall, precipitation. Confirm names and units against the API docs and record the units.
- Licensing: Open-Meteo's free tier is non-commercial. HRDPS itself is open data from Environment Canada, so it is a fallback. Keep raw API responses out of git.

Terrain grid (DEM):
- DEM source to decide: NRCan HRDEM where coverage exists, otherwise a 30 m global DEM.
- Derived per point: elevation, slope, aspect, curvature, relative position (ridge, gully, basin), and upwind exposure features.
- Terrain classes: ridge, couloir, glacier, basin or valley, rock, snow-covered terrain. Start with rule-based classes from the DEM.
- Use DEM elevation, not GPX elevation. Every track checked so far tops out 20 to 70 m below its published summit height.

Route points:
- Sample every about 250 m along each GPX route. Each point stores elevation, terrain features, its `cell_id`, and its elevation offset from the cell.
- Timed 1 Hz tracks must be thinned to about one point per 10 s before measuring distance. Raw 1 Hz distance on the North Victoria track was 33.0 km against 24.97 km after thinning (Strava reports 24.83 km).

Labels:
- Own field observations, MIN public reports, Sentinel-2 and SAR imagery, and photos.
- For other people's reports and photos, store the link, date, author, and extracted facts, not copies.
- Public observation logs exist along the French-Haig-Robertson traverse (for example avalog.co entries with coordinates and snow depths). Check their terms before using them as labels.

### Route set (files received and checked 2026-11-17)

Athabasca, Silverhorn (CalTopo track):
- 1,403 cleaned points, 10.49 km, +1,598 m, max 3,457 m. Timed, dated 2025-06-27, about 9 hours. That date is inside the HRDPS archive, so weather can be backfilled for it.
- Starts at the Icefield area (52.21005, -117.22456, 2,034 m). Ends within 23 m of the Mountain Project coordinate (52.181, -117.20124), about 34 m below the published 3,491 m summit.
- Not yet verified: whether the line goes over Silverhorn or up the North Glacier. Ownership and origin of the track also to confirm. Treat as third-party and git-ignored until confirmed.
- Access note from Mountain Project: the Ice Field snocoach gate is closed during business hours.

Lake Louise, North Victoria (own Strava export):
- 24.97 km after thinning, +1,847 m with a 3 m noise threshold (Strava shows +2,233 m using its own elevation correction), max 3,392 m. 2026-10-16, 12 h 35 min elapsed, 6:39 moving.
- As far as I know the summit is about 3,464 m, so the track stops or reads about 70 m low. Check against memory of the day.
- Strava's logged weather for the activity (about 0 C, 3.6 km/h SW wind) is a model estimate, not a measurement.
- This is the only track committed to the public repo. Before committing, check Strava privacy zones, or trim the start and end, because the file shows exact times and a start location.

Burstall, Sir Douglas West Ridge (TrailAmigo GPX):
- 814 points, 13.99 km, +1,862 m, 1,898 m to 3,385 m. One-way only: the return leg is not in the file, although the page lists 28 km and +2,256 m round trip. No timestamps. Ends about 20 m below the published 3,406 m.
- Four waypoints (a restroom and three OSM glacier points). The file carries a Trail Amigo copyright and licence tag, so do not redistribute it or commit it to a public repo.
- Rockfall hazard is significant on this peak.

Burstall, French-Haig-Robertson ski traverse (AllTrails GPX):
- 3,953 cleaned points, 20.91 km, +1,093 m, 1,893 m to 2,877 m. A loop that starts and ends at the same trailhead. No timestamps, so it cannot be tied to a specific weather day.
- Crosses the Haig Glacier to the Robertson/Sir Douglas col, which has obvious avalanche potential.
- Starts about 20 m from the Sir Douglas West Ridge start. The two routes share the Burstall trailhead and most weather cells.

GPX handling rules:
- Third-party tracks are reference geometry only. Do not redistribute them or commit them to a public repo. They live in a git-ignored folder.
- Glacier tracks are not safe lines: crevasses and snow bridges change every season.
- Record the source, download date, and licence or terms note for every track in the database and in the committed manifest.

## 5. Proposed tables

`peaks`, `regions`, `routes`, `route_points`, `weather_cells`, `forecast_snapshots` (issue time, valid time, lead hours, model, variables), `observations`, `observation_evidence` (source, link, exact supporting text or photo), `terrain_features`, `exposure_scores` (method version, inputs, output), `route_sources` (track source, download date, terms note).

Rules: keep raw API responses; keep observation date separate from publication date; every derived value records its method version; every route belongs to one region. Store all times in UTC.

## 6. Field observation template

One entry per observation, with a short plain sentence after the fields.

- Time and GPS and elevation (from the watch track).
- Forecast carried: source and issue time.
- Wind: speed, direction, method (measured or estimated), sustained or gust.
- Air temperature (shaded), precipitation type.
- Snow: surface type, penetration (boot or ski), new snow depth, wind-transport signs (plumes, cornices, scoured or loaded).
- Avalanches: aspect, elevation, size, type, apparent age, trigger.
- Glacier: bergschrund open or bridged, bridge quality.
- Cloud and visibility, photo filenames.
- Also log negatives such as "stable, nothing observed", to limit selection bias.

Keep a separate held-out set of messy real reports (guide reports and forum posts) for testing the extraction model later, because clean templated entries differ in style.

## 7. Prototype 0 scope

1. Load the GPX for each route; thin timed tracks; sample route points.
2. Daily collector for forecasts, with tests for missing values, duplicates, bad units, and timestamps.
3. Backfill from the archive (the dated Athabasca track and North Victoria are natural first cases); use backfill until the Mini PC is running.
4. DEM features per route point and one peak's terrain classification map.
5. First exposure index (B0 and M1) on one peak, inspected visually against photos and observations.
6. Field template in use; backfill the 8 completed summits from photo times and GPS, tagged low confidence.
7. GitHub research log: hypothesis, data, method, result, interpretation.

Done when: the collector has run for at least 30 consecutive days across the 3 regions (or archive-backfilled equivalent), tests pass, one peak's terrain classes and exposure index are produced reproducibly from the repository, and at least 10 field observations are in the database.

### Build order

Module 1: route points (steps 1 above).
Module 2: weather collector and backfill (steps 2 and 3 above).
Module 3: DEM terrain features (step 4).
Module 4: first exposure index (step 5).
Module 5: field template and summit backfill (step 6).
Research log runs alongside every module (step 7).

The first Claude Code prompt covers Modules 1 and 2 only. Claude Code stops after each module to teach and quiz.

### Module 1 acceptance checks

- The repo runs from a clean checkout with `uv sync` and `uv run pytest`.
- Every loaded track has a `route_sources` row.
- Thinning the North Victoria track gives about 24.97 km, against 33.0 km raw.
- Route totals match the hand-checked values within a stated tolerance: Silverhorn 10.49 km and +1,598 m; Sir Douglas West Ridge 13.99 km; FHR loop 20.91 km.
- Route points sit about 250 m apart along each route.
- No third-party GPX file is tracked by git.

### Module 2 acceptance checks

- Each unique weather cell is fetched once and has a `cell_id`.
- Issue time and valid time are separate fields in `forecast_snapshots`.
- Raw API responses are kept in git-ignored `data/raw/`.
- Running the collector twice makes no duplicate rows.
- Tests cover missing values, duplicates, wrong units, and bad timestamps, using saved sample responses and no live network.
- Backfill works for the 30, 30, and 90 day windows and the two single dates, and any limit on issue-time information is documented.
- The daily scheduled run is not switched on.

## 8. Output wording rules (hard rules)

- Show a relative exposure index, labelled "relative exposure to potential wind loading", not a hazard rating.
- Every output includes evidence, data age, uncertainty, and a link to the official Avalanche Canada bulletin.
- Never say safe, unsafe, go, or no-go.
- Do not use a colour scale that resembles the official 5-level avalanche danger scale.
- A model output is never presented as an official warning or a verified observation.

## 9. Working rules

- Claude Code drafts each module with tests, then teaches it in easy words, then quizzes McKinley. The next module begins only after McKinley passes. Each teaching session and quiz result is logged in `docs/learning-log/`.
- No multi-agent orchestration or vector database in Prototype 0. Revisit analog search once there is enough data.
- Create folders only when a component exists. Use a conventional Python package layout with raw and processed data separated and tests alongside the code.
- Do not publish scraped copyrighted material or restricted datasets.
- Do not claim something works until it has been run. State plainly what could not be checked.

## 10. Out of scope for Prototype 0

Full snowpack physics, route-level avalanche forecasting, autonomous warnings, Facebook scraping, time-decay estimation, Bayesian updating, kriging and Gaussian process work, the website agent, commercial use.

## 11. Open questions

- Whether the Silverhorn track goes over Silverhorn or up the North Glacier, and where it came from.
- A return-leg or full round-trip track for Sir Douglas, if one is needed.
- Whether North Victoria stays as the Lake Louise peak, and why its track tops out about 70 m below the summit.
- DEM source and resolution per region.
- Exact number of weather cells per route, once the API returns its grid coordinates.
- What issue-time information Open-Meteo gives for archived forecasts.
- Which public weather stations near each region can serve as independent wind and temperature checks.
- Mini PC timeline.
- How points per peak should expand from route points toward a mountain-wide grid.
- Whether MIN, avalog, and Sentinel data coverage is dense enough around the chosen regions to be useful.
- Strava privacy zones, or trimming, for the committed North Victoria track.
