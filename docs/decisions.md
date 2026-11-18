# Decisions log

Decisions Claude made while building, with the reason for each, so McKinley can
check them. Newest first within each module. Anything marked **Needs McKinley**
is also listed in [needs-from-mckinley.md](needs-from-mckinley.md).

## Working agreement (2026-11-18)

- McKinley asked Claude to keep building, testing and researching without
  stopping, and to teach and quiz **only when McKinley asks**. This overrides
  the stop-after-every-module rule in `CLAUDE.md` for this session. The
  learning log (`docs/learning-log/`) starts when the first teaching session
  happens.
- The project lives in `mckinleytysdal/mountain-software-vo1`, not in the
  11,000ers site repo. The site repo is only read (see Module 1, D7).

## Module 1: route points

**D1. Standard-library GPX parser, no GPX package.** `xml.etree` reads GPX 1.0
and 1.1 in about 80 lines. Every line can be read and taught; one less
dependency to trust.

**D2. "Cleaning" means two things only:** drop impossible coordinates (outside
±90/±180, or exactly 0,0) and drop back-to-back repeats of the same position.
It does not smooth or remove spikes. SPEC.md quotes "cleaned point" counts
(1,403 Silverhorn, 3,953 FHR); the real-data test checks whether this
definition reproduces them. If it does not, the definition used for the hand
check needs to be found, not guessed.

**D3. Thinning rule:** keep the first point, then the next point at least
10 s after the last kept one, and always the last point. Applied only when
the track is timed and its median gap is under 10 s. Untimed tracks are left
as they are.

**D4. Elevation gain uses a 3 m hysteresis threshold** on GPX elevation, after
thinning. The climb is counted only once you are 3 m above the last
reference; a 3 m drop resets the reference. This matches the "3 m noise
threshold" in SPEC.md.

**D5. Route points are placed every 250 m of along-track distance,** by
straight-line interpolation between track points, starting at the first
point and always ending at the last point (so the final gap is shorter).
Distances use the haversine formula on a 6,371,008.8 m sphere.

**D6. One `route_sources` row per route** (primary key = `route_id`), holding
source, URL, file name, SHA-256 of the file, download date, terms note, the
GPX `creator`, copyright author and licence tags, and two flags:
`redistribution_allowed` and `committed_to_repo`. The committed
`data/routes/manifest.toml` holds the same facts, so the manifest is the
human-readable source and the table is its copy.

**D7. North Victoria verification used the 11,000ers site geometry.** The
Strava GPX is on McKinley's computer, not in this cloud session. The site repo
already publishes a simplified copy of the same recording
(`src/data/tracks/victoria-north.json`, 867 points, no times). Claude decoded
it into the git-ignored `data/routes/local/` folder to test the pipeline and
find real weather cells. Result: 24.20 km, +1,896 m GPX gain, max 3,384 m,
98 route points. It cannot check the 33.0 km raw / 24.97 km thinned numbers,
because the site copy has no timestamps.

**D8. North Victoria's summit is the north peak, 3,388 m.** SPEC.md said
"about 3,464 m, so the track reads about 70 m low". 3,464 m is the south
(main) summit of Mount Victoria. The site lists the north peak at 3,388 m,
and the track tops out at 3,384 to 3,392 m, so the track is within a few
metres. The manifest now uses 3,388 m. **Needs McKinley** to confirm.

**D9. Own tracks are git-ignored until cleared.** `data/routes/own/*.gpx` is
ignored. To commit the North Victoria file after the privacy check, add a
`!data/routes/own/<file>` line to `.gitignore` and set
`committed_to_repo = true` in the manifest. A test fails if any GPX is
tracked that the manifest does not mark as committed.

**D10. Expected file names.** The manifest names where each GPX file should
go (for example `data/routes/third_party/silverhorn_caltopo.gpx`). McKinley
renames the files to match, or edits the `file` field.

**D11. Real-data tests use stated tolerances:** distance 1 %, GPX gain 5 %,
maximum GPX elevation 5 m, clean point count exact. They skip when a file is
missing, so a clean checkout passes.

## Module 2: weather collector and backfill

**D12. Three Open-Meteo services, each for one job** (details in
[weather-data.md](weather-data.md)):
- Forecast API: only to find which grid cell each route point is in.
- Single Runs API (`run=` parameter): true forecasts with a known issue time.
  Archive from 2026-04-02. Used for the daily collector and for backfill.
- Historical Forecast API: stitched series back to 2023-03-03 with no issue
  time. Stored as `product = 'historical_stitched'` with `issue_time_utc`
  NULL, and never called a forecast.

The Previous Runs API (fixed 24 h, 48 h, ... offsets) is not used yet. Single
runs give the exact issue time, which is stronger. Previous Runs can be added
for lead-time error work later.

**D13. Raw model values, not Open-Meteo's mountain correction.** By default
Open-Meteo picks a nearby "land" cell with similar elevation and adjusts
temperature to a 90 m DEM height at the requested point. Claude requests
`cell_selection=nearest` and `elevation=nan`, which returns the nearest grid
cell's own values and its model elevation. Reason: the spec wants each cell
fetched once and shared by all its route points; downscaled values would
differ per point. The elevation difference between route point and cell is
stored (`ele_offset_gpx_m`) so a correction can be applied later, openly.

**D14. A cell is named by the grid coordinates the API returns,** rounded to
6 decimals, per model. Cell discovery sends route point coordinates in
batches of 50 and reads back the grid coordinates. Before storing a forecast,
the collector checks the API used the same grid coordinates again ("cell
drift" check).

**D15. Units are requested explicitly** (`celsius`, `kmh`, `mm`, timezone
GMT) and checked on every response. A mismatch stops the write. Columns carry
the unit in their name (`wind_speed_10m_kmh`), and each fetch stores the unit
strings it received.

**D16. Database guarantees, not just code:** a CHECK constraint makes a
single-run row carry an issue time and lead hours, and a stitched row carry
neither. A unique index on (cell, model, product, issue time or 'unknown',
valid time) makes duplicates impossible; writes are upserts.

**D17. Backfill run hours default to 00 and 12 UTC** (2 runs a day). HRDPS runs
4 times a day; fetching all 4 for 90 days doubles the calls for little gain at
this stage. `--run-hours 0,6,12,18` gets all four. For a single trip date,
runs start the day before (the forecast a party would have carried).

**D18. "Last N days" = the N whole UTC days ending yesterday.**

**D19. The free tier is shared and flaky from this cloud session.** The API
sometimes answers "Daily API request limit exceeded" after a few calls, most
likely because the cloud egress IP is shared. The collector retries with
back-off, stops a backfill cleanly when still limited, and skips runs already
stored, so a rerun continues where it stopped. On the Mini PC this should be
rare.

**D20. The daily schedule is not switched on.** `uv run mountain weather
collect` is the command a scheduler would run. No cron job, systemd timer or
cloud schedule exists.
