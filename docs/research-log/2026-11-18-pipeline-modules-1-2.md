# 2026-11-18: Route points and weather cells (Modules 1 and 2)

Status: exploratory. Engineering checks only; no research result yet.

## Hypothesis
None tested yet. This entry records what the data foundation can and cannot
support.

## Data
- North Victoria geometry from McKinley's own track (simplified site copy,
  867 points, no timestamps). The other three tracks were not available in
  the build session.
- GEM HRDPS Continental through Open-Meteo: single runs 2026-10-15 00Z to
  2026-10-16 18Z, stitched archive for 2026-10-16.

## Method
GPX -> clean -> (thin if timed) -> 250 m route points -> nearest HRDPS cell
(`cell_selection=nearest`, `elevation=nan`).

## Result
- North Victoria: 24.20 km, 98 route points, 5 HRDPS cells.
- Route points sit up to about 1,000 m above their cell's model elevation
  (summit cell model height 2,345 m; summit 3,388 m). Lower route points sit
  up to about 340 m below their cell's model height.
- Every single run reports no precipitation or snowfall at lead hour 0.

## Interpretation
The model surface is far smoother than the mountain. Model 10 m wind at a
summit cell describes wind over a 2,345 m surface, not over a 3,388 m ridge.
Any exposure index must treat model wind as a regional driver and get local
exposure from the DEM. This supports the M1 design in SPEC.md, but proves
nothing yet.

## What could not be checked
- The 33.0 km raw / 24.97 km thinned North Victoria numbers (needs the timed
  Strava file).
- Silverhorn, Sir Douglas and FHR numbers and cell counts (files not present).
