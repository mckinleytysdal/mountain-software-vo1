# 2026-11-19: All three regions, real cells, three stations

Status: exploratory. No hypothesis tested yet (still no wind-effect labels).

## Data
- All four tracks loaded (North Victoria from McKinley's full Strava file,
  101 route points; the three third-party tracks local only).
- HRDPS cells from the API: Icefield 2, Lake Louise 5, Burstall 9 (Sir
  Douglas 6, FHR 7, 4 shared): 16 in all.
- Backfill: Icefield and Burstall last 30 days, Lake Louise last 90 days,
  00Z and 12Z runs plus the stitched archive; 2026-11-16 12Z run missing from
  the archive in every region. Silverhorn 2025-06-27: stitched only.
- Stations: Bosworth Upper, Tangle Ridge, Burstall Pass, each on its own cell.

## Results
1. **Station check (docs/stations.md):** the height blend of 10 m and 700 hPa
   wind was best or equal-best at all three stations (MAE 6.5, 10.0 and
   4.2 km/h). 10 m wind never reached 25 km/h at either ridge station; at the
   sheltered Burstall Pass station 700 hPa wind would be 28 km/h too strong
   and the blend falls back to 10 m wind by itself.
2. **The same storms drive all regions.** Over 2026-10-23 to 11-18 the daily
   loading series of the four routes correlate 0.84-0.99. The strongest
   windows everywhere were 8-9 November and 12-13 November, with 700 hPa wind
   of about 75-88 km/h from 225-247° (SW to WSW).
3. **How much each route "sees" depends on how high it sits above the model
   ground.** Mean loading per route point per day: Silverhorn 35.7, North
   Victoria 7.3, Sir Douglas 0.34, FHR 0.22. Silverhorn's points are mostly
   well above their cells (2,412-2,607 m), so they get close to full ridge
   wind; most Burstall points are near or below their cells (2,192-2,615 m) and
   get mostly 10 m wind. The index is a rank within a route, so these levels
   are not a comparison of hazard between routes.
4. **B0 and M1 disagree more than they agree.** Median daily rank
   correlation: North Victoria 0.37, Silverhorn 0.24, Sir Douglas 0.29,
   FHR 0.08.

## Interpretation
The data foundation now covers all three regions with true forecasts. The
blend choice is supported by three independent stations. Whether M1's
different ranking is better than B0's is still untested; the next step is
labelled observations, ideally from the 8-9 or 12-13 November storms or the
next one.
