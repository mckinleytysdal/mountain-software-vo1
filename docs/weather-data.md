# Weather data: what the APIs really give

Checked against the Open-Meteo documentation and live calls on 2026-11-18.
Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0);
HRDPS model data from Environment and Climate Change Canada.

## Model

GEM HRDPS Continental, Open-Meteo id `gem_hrdps_continental`: 2.5 km grid,
hourly values, 48-hour forecasts, runs at 00, 06, 12 and 18 UTC.

| Variable (API name) | Unit we require | Meaning |
|---|---|---|
| `temperature_2m` | °C | air temperature 2 m above the model surface, instant |
| `wind_speed_10m` | km/h | wind 10 m above the model surface, instant |
| `wind_direction_10m` | ° | direction the wind blows **from** (0 = north) |
| `wind_gusts_10m` | km/h | maximum gust in the preceding hour |
| `snowfall` | cm | snow in the preceding hour (Open-Meteo: divide by 7 for mm water) |
| `precipitation` | mm | rain + snow (water equivalent) in the preceding hour |

## Issue time: what we can and cannot know

| Product (our name) | Service | Archive from | Issue time | Called a forecast? |
|---|---|---|---|---|
| `single_run` | Single Runs API, `run=YYYY-MM-DDTHH:MM` | 2026-04-02 | Yes: the requested run time | Yes |
| `historical_stitched` | Historical Forecast API | 2023-03-03 | **No**: first hours of each run glued together; the API does not say which run | No |
| (not used yet) | Previous Runs API | Jan 2024 for most models; HRDPS start not stated | Approximate: fixed 24 h × N offsets, run not named | Not yet |

Consequences for the backfill windows:

| Window | True forecasts (single runs) | Stitched |
|---|---|---|
| Icefield, last 30 days | yes | yes |
| Burstall, last 30 days | yes | yes |
| Lake Louise group, last 90 days | yes | yes |
| North Victoria, 2026-10-16 | yes (runs from 2026-10-15) | yes |
| Silverhorn, 2025-06-27 | **no**: before 2026-04-02 | yes, issue time unknown |

So the Silverhorn day can be described with model weather, but not with "the
forecast you would have read that morning". That is recorded honestly in the
database (`issue_time_known = 0`, note on the fetch row).

## Observed behaviour worth knowing

- **Lead hour 0 has no accumulations.** In every single run, `precipitation`
  and `snowfall` are `null` at the run time itself, because they are "preceding
  hour" totals. They are stored as NULL and counted as missing.
- **The response `elevation` depends on the request.** Without `elevation=nan`
  it is the 90 m DEM height of the point you asked for, and temperature is
  adjusted to it. With `elevation=nan` it is the model cell's own height and
  the values are raw. We use `elevation=nan`.
- **Default cell choice is not the nearest cell.** With the default
  `cell_selection=land`, a point near Lake Louise was given a cell about 3 km
  away with closer elevation. We use `cell_selection=nearest`.
- **Model terrain is smooth.** On North Victoria the highest route points are
  about 1,000 m above their cell's model surface (cell at 2,345 m, summit
  3,388 m). Model "10 m wind" is wind over a smoothed mountain, not ridge-crest
  wind. This is a known limitation and a reason the exposure index needs
  terrain from a DEM.
- **Rate limits.** From this cloud session, calls were intermittently refused
  with "Daily API request limit exceeded", probably a shared IP. Free-tier
  limits are 600/min, 5,000/h, 10,000/day; a request over 10 variables or
  2 weeks per location counts as more than one call.

## Real cell count

| Region | Cells | Source of route points |
|---|---|---|
| Lake Louise (North Victoria) | 5 | site copy of McKinley's track (98 route points) |
| Columbia Icefield | not yet | needs the Silverhorn GPX |
| Burstall | not yet | needs the Sir Douglas and FHR GPX |

Run `uv run mountain weather cells` after loading the GPX files to fill this in.
