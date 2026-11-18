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

## Module 3: DEM terrain features

**D21. DEM = NRCan MRDEM-30 DTM** (30 m, bare earth, Canada-wide, one
cloud-optimised GeoTIFF, Open Government Licence - Canada 2.0, EPSG:3979).
A route's window is read over HTTP in about a second and cached in
git-ignored `data/raw/dem/`. NRCan HRDEM (1-2 m lidar) was checked: the STAC
catalogue lists a mosaic tile and a BC East Kootenay lidar project near Lake
Louise, but the Alberta side is unlikely to be covered. HRDEM is a later
upgrade where coverage exists. Copernicus GLO-30 is reachable as a fallback.

**D22. Aspect is converted from grid north to true north.** In EPSG:3979 grid
north is about 19° off true north at North Victoria (central meridian
-95°). Without the correction every aspect, and every leeward test, would be
19° wrong. The convergence is stored per route point. Wind directions are
converted the other way before Sx is computed.

**D23. Features per route point:** DEM elevation (bilinear), slope and aspect
(Horn 1981), curvature (minus the Laplacian; positive = convex), TPI at
150 m and 1,000 m (raw and standardised over the window), Weiss slope
position from the 1,000 m TPI, a rule-based landform class, and Sx.

**D24. Landform classes (method terrain-v2), first rule wins:** ridge
(small TPI > +1 SD, or > +0.5 SD on high ground), couloir/gully (small TPI
< -1 SD and slope >= 30°), basin/valley (large TPI < -0.5 SD and slope <
25°), steep face (slope >= 30°), open slope. Version 1 let the large TPI alone
mark ridges; on the North Victoria map that painted whole upper mountains as
"ridge", so it was replaced (failed approach, kept here on purpose).

**D25. Glacier, rock and snow are surface classes, kept separate** from
landform and stored as `unknown` until glacier outlines (RGI) and imagery
(Sentinel-2) are added.

**D26. Sx (Winstral et al. 2002) for 36 wind directions** (every 10°, true
north), each averaged over a 30° window in 5° steps, at search distances
100 m and 300 m. Positive = sheltered by higher ground upwind, negative =
exposed. Parameters are stored with every row and are pending a literature
check (see the research log).

**D27. Map colours are categorical** (purple, blues, teal, brown, grey) and
avoid the green-yellow-orange-red-black danger scale. The map has a true-north
arrow because the grid is drawn grid-north-up.

## Module 4: first exposure index

**D28. Output = "relative exposure to potential wind loading"**, a rank from
0 to 1 among the points of one route for one time window. When every point
scores the same (for example no transport at all), the index is left empty
and the report says "no result for this window", rather than showing 0.5
everywhere.

**D29. B0 baseline:** leeward when aspect (true north) is within ±45° of the
downwind direction. Reported per point as the fraction of hours leeward.

**D30. M1 (method m1-sx-transport-v2):** for each hour,
transport = ((U - Ut) / Ut)^3 above the threshold Ut (25 km/h), times a snow
supply term (0.2 for old snow, rising to 1 with 20 cm of snowfall in the
previous 72 h), times sin(Sx) for that hour's wind direction (100 m search).
Positive Sx adds to loading, negative to scour. Net = loading - scour,
summed over 72 h. Every constant is a parameter stored with the result and
is a first guess pending the literature check.

**D31. Ridge-top wind drives M1, not 10 m wind.** In 90 days of HRDPS data
(2026-08-20 to 2026-11-17), the 10 m wind at the North Victoria summit cell
never exceeded 25 km/h (maximum 18 km/h), while 700 hPa wind on a sample day
reached 61 km/h. The 10 m wind sits over a model surface about 1,000 m below
the summit. M1 v1 used 10 m wind and found no transport at all on any day
(failed approach, kept on purpose). The collector now also stores 700 hPa wind
speed, direction, geopotential height and temperature (10 variables, still
one API call per location), and M1 uses 700 hPa wind by default
(`--wind-level 10m` remains available for comparison).

**D32. No look-ahead in the index:** each hour uses the newest model run that
was already published at the as-of time (run time + 3 h publication lag,
from Open-Meteo's 1-3 h figure for regional models). The data age reported is
as-of minus that run time.

**D33. Adding a collector variable makes older runs count as incomplete,** so
a rerun of the backfill fetches them again and fills the new columns by
upsert (no duplicate rows).

## Literature check (2026-11-18)

**D34. Parameters revised after the literature check** (details and citations
in [literature.md](literature.md)): M1 transport now grows with U^4, not U^3
(m1-sx-transport-v3); M1 uses Sx at 300 m by default, 100 m kept as a
sensitivity run; the 25 km/h threshold is tied to Avalanche Canada's
ridge-top wind classes. The MRDEM attribution now credits Copernicus GLO-30,
as its licence requires. The ±45° leeward window and the TPI radii have no
published standard; they stay as stated choices.

## Module 5: field template and observations

**D35. Observations are TOML files** (`templates/field_observation.toml` is the
template), checked by `mountain obs load`. TOML because it is plain text,
readable on a phone, diff-friendly in git, and Python reads it without a
package. Each entry is labelled fields plus one plain sentence, as SPEC.md asks.

**D36. Times must carry a time zone** and are stored in UTC. A bare date is
allowed with `time_precision = "day"`. Observed time and published time are
separate fields, and a published time before the observed time is refused.

**D37. The main label is `wind_effect`** (loaded, scoured, mixed, none_seen,
unknown). The landform and aspect fields are on the observation itself, so a
label can be checked against both the DEM class and the observer's own view.

**D38. Someone else's report must carry a link** (and never a copy of their
text or photos). A quote is allowed only as evidence for one's own writing.

**D39. Observations link to the nearest route point within 300 m** when they
have coordinates, so they can be compared with that point's exposure index.

**D40. Summit backfill from McKinley's published trip reports.** The 8
completed summits are covered by 6 reports on the 11,000ers site. Photo EXIF
GPS and times are stripped from the site copies, so the "photo times and GPS"
route in SPEC.md is not possible from there. Instead, condition statements
were drafted from the report text with the exact quote as evidence,
`confidence = "low"` and `needs_review = true`. They have no coordinates
until McKinley adds them from his original photos or tracks.

## Fixes after an independent code review (2026-11-18)

**D41.** A review of the branch found two real bugs and several risks. Fixed:
- Look-ahead: stitched archive values were used right up to the as-of time,
  although the run behind them was not yet published. They now count only
  when valid time + 3 h <= as-of. Regression test added.
- The 72 h fresh-snow memory only saw snow inside the scoring window; it now
  reads the 72 h before the window too (M1 v4). The window now has exactly
  72 hourly values (start excluded).
- Exposure scoring now uses only the newest DEM's terrain rows and the
  configured weather model.
- `routes load` skips a route whose file and method are unchanged, because a
  reload cascades through the foreign keys and deletes weather links, terrain
  and stored exposure results. `--force` reloads.
- The cached DEM window is refetched when the route reaches outside it.
- Route dates and date-only observations use Rockies local time
  (America/Edmonton), not UTC dates (schema migration 7 renames
  `track_date_utc` to `track_date_local`).
- An observation's `forecast_issue` after its observed time is rejected.
- The threshold applied to 700 hPa wind is intended: Avalanche Canada's wind
  classes describe ridge-top wind. The station check (next) tests this.
