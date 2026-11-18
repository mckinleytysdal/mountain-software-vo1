# Prototype 0 status against SPEC.md

Updated 2026-11-18. "Passed" means checked by a command that was run; the
command is named.

## Module 1 acceptance checks

| Check | Status | How checked |
|---|---|---|
| Runs from a clean checkout with `uv sync` and `uv run pytest` | Passed | full suite, all real-data tests skip cleanly |
| Every loaded track has a `route_sources` row | Passed | `tests/test_routes.py` |
| North Victoria thinning gives ~24.97 km vs 33.0 km raw | **Blocked**: needs the timed Strava GPX | thinning logic tested on synthetic 1 Hz tracks |
| Silverhorn 10.49 km / +1,598 m; Sir Douglas 13.99 km; FHR 20.91 km | **Blocked**: needs the GPX files | `tests/test_realdata.py` ready, 1 % / 5 % tolerance |
| Route points about 250 m apart | Passed | synthetic tests; live North Victoria (98 points) |
| No third-party GPX tracked by git | Passed | `tests/test_repo_hygiene.py` |

## Module 2 acceptance checks

| Check | Status | How checked |
|---|---|---|
| Each unique cell fetched once, with a `cell_id` | Passed | tests; live: North Victoria has 5 cells |
| Issue and valid time separate | Passed | schema CHECK constraints + tests |
| Raw responses in git-ignored `data/raw/` | Passed | tests; hygiene test |
| Twice = no duplicates | Passed | tests; live rerun made 0 API calls |
| Tests for missing values, duplicates, wrong units, bad timestamps, no network | Passed | `tests/test_weather_parse.py`, `tests/test_weather_collector.py` |
| Backfill windows 30/30/90 days and the two dates; issue-time limits documented | Partly: Lake Louise 90 days and 2026-10-16 ran live; Icefield and Burstall need route files; Silverhorn date has stitched values only (documented in `docs/weather-data.md`) | live run |
| Daily schedule not switched on | Passed | nothing scheduled; see `docs/minipc-setup.md` |

## Prototype 0 "done" criteria

| Criterion | Status |
|---|---|
| Collector run for 30 consecutive days across 3 regions (or backfilled equivalent) | Lake Louise: 90 days backfilled. Icefield and Burstall: waiting for GPX files |
| Tests pass | Passed |
| One peak's terrain classes and exposure index produced reproducibly | North Victoria: landform map and M1/B0 run, from the repo commands plus the local track copy |
| At least 10 field observations in the database | Draft observations from trip reports exist (low confidence, need review); no new field observations yet |
