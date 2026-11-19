# Prototype 0 status against SPEC.md

Updated 2026-11-19. "Passed" means checked by a command that was run; the
command is named.

## Module 1 acceptance checks

| Check | Status | How checked |
|---|---|---|
| Runs from a clean checkout with `uv sync` and `uv run pytest` | Passed | full suite, all real-data tests skip cleanly |
| Every loaded track has a `route_sources` row | Passed | `tests/test_routes.py` |
| North Victoria thinning gives ~24.97 km vs 33.0 km raw | Passed: 32.99 km raw, 24.96 km thinned | `tests/test_realdata.py` |
| Silverhorn 10.49 km / +1,598 m; Sir Douglas 13.99 km; FHR 20.91 km | Passed (Silverhorn point count not reproducible, D45) | `tests/test_realdata.py` |
| Route points about 250 m apart | Passed | synthetic tests; live North Victoria (98 points) |
| No third-party GPX tracked by git | Passed | `tests/test_repo_hygiene.py` |

## Module 2 acceptance checks

| Check | Status | How checked |
|---|---|---|
| Each unique cell fetched once, with a `cell_id` | Passed | tests; live: Icefield 2, Lake Louise 5, Burstall 9 cells |
| Issue and valid time separate | Passed | schema CHECK constraints + tests |
| Raw responses in git-ignored `data/raw/` | Passed | tests; hygiene test |
| Twice = no duplicates | Passed | tests; live rerun made 0 API calls |
| Tests for missing values, duplicates, wrong units, bad timestamps, no network | Passed | `tests/test_weather_parse.py`, `tests/test_weather_collector.py` |
| Backfill windows 30/30/90 days and the two dates; issue-time limits documented | Passed: all windows ran live on 2026-11-19; Silverhorn date has stitched values only (documented) | live run |
| Daily schedule not switched on | Passed | nothing scheduled; see `docs/minipc-setup.md` |

## Prototype 0 "done" criteria

| Criterion | Status |
|---|---|
| Collector run for 30 consecutive days across 3 regions (or backfilled equivalent) | Passed by backfill: 30 / 30 / 90 days |
| Tests pass | Passed |
| One peak's terrain classes and exposure index produced reproducibly | North Victoria: landform map and M1/B0 run, from the repo commands plus the local track copy |
| At least 10 field observations in the database | Draft observations from trip reports exist (low confidence, need review); no new field observations yet |

## Beyond the checklist

- Model wind checked against three stations on their own cells (`docs/stations.md`).
- 77 draft observations from the trip reports, all needing review, none with a wind-effect label.
