# Checking model wind against a ridge-top station

Only summary statistics are published here. Avalanche Canada's terms do not
allow reproducing their station data without consent, so the hourly values
stay in git-ignored `data/raw/` and the local database.

## Stations chosen (search on 2026-11-18)

| Region | Station (Avalanche Canada id) | Elevation | Why |
|---|---|---|---|
| Lake Louise | Bosworth Upper (111), Parks Canada | 2,745 m | ridge-top wind and temperature, ~10 km from North Victoria |
| Columbia Icefield | Tangle Ridge (129), Parks Canada | 3,009 m | only current ridge-top station nearby |
| Burstall | Burstall Pass (1), Kananaskis Country | 2,300 m | on site; wind, temperature, snow depth |

Long-record alternatives: ECCC Yoho Park (11790J1, 1,602 m) and ECCC Nakiska
Ridgetop (305MGFF, 2,543 m), both Open Government Licence. Avalanche Canada's
API: `https://weather.prod.avalanche.ca/stations/{id}/measurements`, no key,
archive from about December 2023. Times are UTC: the station's warmest hour
on average is 21 UTC (15:00 MDT).

## Result 1: Bosworth Upper vs HRDPS, 2026-08-20 to 2026-11-17

2,160 paired hours. Provisional: the model values are from the stored HRDPS
cell nearest the station (8.8 km away, model height 2,168 m), because the
Open-Meteo daily limit was used up before the station's own cell could be
fetched. Redo with `validation.stations.station_cell` when the limit resets.

| Model wind | Station mean | Model mean | Bias | MAE | r | Hours >= 25 km/h (station 921) |
|---|---:|---:|---:|---:|---:|---|
| 10 m | 24.4 | 6.9 | -17.4 | 17.6 | 0.61 | model 0 |
| 700 hPa | 24.4 | 28.7 | +4.3 | 8.2 | 0.78 | model 1,098, both 802 |
| blend by height (weight 0.69) | 24.4 | 20.8 | -3.6 | 7.2 | 0.79 | model 692, both 586 |

Units km/h. Bias = model minus station.

| Wind direction (station wind >= 10 km/h) | Mean difference | Within 45° |
|---|---:|---:|
| 10 m | 52° | 51% |
| 700 hPa | 63° | 26% |
| blend | 61° | 28% |

| Temperature | Bias | MAE | r |
|---|---:|---:|---:|
| 2 m (cell at 2,168 m) | +0.7 °C | 2.5 °C | 0.91 |
| 700 hPa | -1.4 °C | 2.2 °C | 0.92 |

## Interpretation

- HRDPS 10 m wind badly under-reads ridge-top wind here: it never reached the
  25 km/h transport threshold while the station passed it in 43% of hours.
  Driving M1 with 10 m wind would show almost no snow transport.
- Mixing 10 m and 700 hPa wind by height gives the smallest error and keeps
  valley points from getting ridge-top wind. M1 now uses it (m1 v5).
- Direction at this one station is matched better by 10 m wind than by
  700 hPa wind, probably because the ridge steers the local flow. One
  station is not enough to change the method; the "hybrid" option (700 hPa
  speed, 10 m direction) exists to test this when more labels exist.
