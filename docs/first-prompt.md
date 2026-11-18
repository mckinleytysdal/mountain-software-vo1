# First prompt for Claude Code

Paste everything under the line into Claude Code, in an empty repo folder that contains `SPEC.md` and `CLAUDE.md`.

---

You are helping me build Mountain Software, a public research and resume project. Read `SPEC.md` and `CLAUDE.md` in this repo first. They hold every decision already made, so do not interview me again. If you are truly blocked, ask one short question at a time.

I am learning Python. I want to understand every line. Follow the teach-then-quiz rule in `CLAUDE.md` exactly.

## Your job in this session

Build Module 1 only. Then stop, teach, and quiz me. Build Module 2 only after I say "start Module 2".

### Step 0: plan first

Before writing code, show me a short plan in plain words: the folder layout, the database tables for Module 1, and the order you will build things. Wait for my "ok".

### Module 1: route points

Goal: turn each GPX file into clean, evenly spaced route points stored in SQLite.

1. Set up the repo with `uv`, `pyproject.toml`, a conventional package layout, `pytest`, and a `.gitignore`. The `.gitignore` must exclude third-party GPX files, raw weather data, and SQLite database files. Do not commit any third-party GPX file.
2. Create SQLite tables: `regions`, `peaks`, `routes`, `route_points`, `route_sources`. Every route belongs to one region. Every track has a `route_sources` row with source, download date, and terms note.
3. Write a GPX loader. Store GPX elevation but label it clearly as GPX elevation. Terrain elevation comes later from a DEM.
4. Thin timed 1 Hz tracks to about one point per 10 seconds before measuring distance.
5. Sample one route point about every 250 m along each route.
6. Write a committed manifest of every track (source, download date, terms note).
7. Write tests. Check against the numbers in `SPEC.md`:
   - North Victoria: about 33.0 km raw and about 24.97 km after thinning.
   - Silverhorn: 10.49 km, +1,598 m.
   - Sir Douglas West Ridge: 13.99 km.
   - French-Haig-Robertson loop: 20.91 km.
   - Route points sit about 250 m apart.
   - Because the third-party files are not committed, tests for them must use tiny synthetic GPX fixtures you create. Only the real-data check is run locally against the files in the git-ignored folder, and it is skipped when the files are missing.

The GPX files are on my computer. Tell me which folder to put them in, and wait for me to do it. Do not search my computer for them.

### After Module 1: stop and teach

Do not start Module 2. Do the teach-then-quiz steps from `CLAUDE.md`: easy words, analogies, each key function with an example, what each test proves, what you could not check, then a quiz of 3 to 5 questions one at a time. Save a note in `docs/learning-log/`. Wait.

### Module 2 (only after I say "start Module 2")

Goal: a weather collector with backfill.

1. Fetch forecasts from Open-Meteo using the HRDPS model (2.5 km). Check the current API docs for the exact endpoints, variable names, and units, and record the units.
2. Variables: temperature, wind speed, wind direction, wind gusts, snowfall, precipitation.
3. Work out the real weather grid cells from the grid coordinates the API returns. Give each unique cell one `cell_id` and fetch it once. Tell me the real cell count per region.
4. Create `weather_cells` and `forecast_snapshots`. Store forecast issue time and valid time as separate fields, with lead hours and model. Store all times in UTC.
5. Save every raw API response in git-ignored `data/raw/`, plus tidy rows in SQLite.
6. Make the collector safe to run twice with no duplicate rows.
7. Add a backfill mode for these windows:
   - Columbia Icefield: last 30 days.
   - Burstall: last 30 days.
   - Lake Louise group: last 90 days.
   - Single dates: Silverhorn on 2025-06-27, North Victoria on 2026-10-16.
8. Check what issue-time information the archive API really gives for past forecasts. If it cannot give a true issue time, record that honestly and explain it to me. Do not label such values as true forecasts.
9. Write tests for missing values, duplicates, wrong units, and bad timestamps. Use saved sample responses. Tests must never use the live internet.
10. Do not switch on any daily schedule. The Mini PC does not exist yet.

Then stop, and do the teach-then-quiz steps again.

## Rules that never change

- Never write safe, unsafe, go, or no-go. Never present a model output as an official warning.
- Do not say something works until you have run it. Show what you ran, and say what you could not verify.
- Only build what the current module needs. No vector database, no multi-agent tools, no website.
- My own North Victoria Strava track may be committed, but ask me about Strava privacy zones or trimming first. Every other track stays out of git.
