# 2026-11-18: Terrain, first exposure index, and what the trip reports can label

Status: exploratory. No hypothesis tested yet.

## Data
- North Victoria route geometry (own track, site copy), 98 route points.
- NRCan MRDEM-30 window around the route.
- HRDPS single runs (00Z and 12Z) and the stitched archive, 2026-08-20 to 2026-11-17, Lake Louise cells.
- 77 draft observations from McKinley's 6 published trip reports (8 summits).

## Results
1. **10 m model wind is almost always below transport thresholds here.** At
   the North Victoria summit cell (model height 2,345 m), hourly 10 m wind
   never exceeded 25 km/h in 90 days (maximum 18 km/h). 700 hPa wind (about
   3,000 m) on 2026-11-08 ranged 40-61 km/h while 10 m wind was 9-18 km/h.
   M1 v1, driven by 10 m wind, found no transport on any day. This is a
   documented failed approach; M1 now uses 700 hPa wind.
2. **The 72 h before the North Victoria climb (2026-10-16) were quiet:**
   10 m wind <= 22 km/h and about 0.1 cm model snowfall per cell. McKinley's
   report describes "favourable conditions and firm snow on the way up",
   which is consistent with little recent transport, but one day proves
   nothing.
3. **Grid convergence matters:** aspect computed in EPSG:3979 is about 19°
   off true north at Lake Louise. Without the correction every leeward test
   would be shifted.
4. **Landform rule v1 failed:** using the 1,000 m TPI alone painted whole
   upper mountains as "ridge". v2 requires a high 150 m TPI.
5. **Trip reports give conditions, not wind-effect labels.** All 77 draft
   observations have `wind_effect = unknown`: the text never states that snow
   was wind-loaded or scoured, though it mentions cornices, firm or soft snow,
   whiteouts and verglas. To test M1 against B0, observations need the
   explicit loaded/scoured field, which the field template now asks for.

## Interpretation
The pipeline runs end to end on one peak, but the research question cannot
be tested yet: there are no wind-effect labels. The cheapest next labels are
(a) McKinley's own field entries with the template, (b) Avalanche Canada MIN
reports that mention wind slabs or cornices with a location, and (c)
Sentinel-2 imagery of scoured versus loaded slopes after a wind event.

## Later the same day: station check

- Bosworth Upper (2,745 m) vs HRDPS over 90 days: 10 m model wind mean
  6.9 km/h against 24.4 km/h measured; 700 hPa wind +4.3 km/h bias, r 0.78.
  A height-weighted blend of the two had the lowest error (MAE 7.2 km/h).
- With the blend (M1 v5), 81 of 86 days show some transport. The strongest
  loading days were 2026-11-08/09, when the station measured up to 39 km/h
  S-SE wind, and the model had about 6 cm of snow. On 2026-11-09 the
  top-ranked points were the upper NE ridge of North Victoria (east-facing,
  3,090-3,360 m), the lee of that S-SW wind.
- Median rank correlation between B0 and M1 across days: 0.32. M1 is no
  longer a restatement of aspect, but whether it is BETTER is still untested:
  there are no wind-effect labels yet.
