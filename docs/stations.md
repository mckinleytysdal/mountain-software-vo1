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

## Result: three stations vs HRDPS, 2026-08-20 to 2026-11-17

Each station is compared with its **own** HRDPS cell (found with
`validation.stations.station_cell`), about 2,160 paired hours each. Bias =
model minus station; typical error = mean absolute error (MAE). km/h.
"Blend" mixes 10 m and 700 hPa wind by the station's height between the model
ground and the 700 hPa height (the wind M1 uses). Rerun with
`validation.stations.compare`.

### Wind speed

| Station (height; model ground) | Model wind | Mean (station 24.4 / 20.1 / 5.4) | Bias | MAE | r | Hours >= 25 km/h caught |
|---|---|---:|---:|---:|---:|---|
| Bosworth Upper (2,745 m; 1,965 m) | 10 m | 7.9 | -16.4 | 16.7 | 0.68 | 0 of 921 |
| | 700 hPa | 32.0 | +7.6 | 10.1 | 0.81 | 863 of 921, 422 false |
| | **blend** | 24.9 | **+0.6** | **6.5** | **0.82** | 748 of 921, 178 false |
| Tangle Ridge (3,009 m; 2,157 m) | 10 m | 3.7 | -16.4 | 16.5 | 0.29 | 0 of 643 |
| | 700 hPa | 28.5 | +8.4 | 10.8 | 0.67 | 555 of 643, 587 false |
| | **blend** | 27.3 | +7.2 | **10.0** | **0.68** | 538 of 643, 534 false |
| Burstall Pass (2,300 m; 2,348 m) | 10 m | 9.3 | +3.9 | 4.2 | 0.74 | station never reached 25 |
| | 700 hPa | 33.3 | +27.9 | 27.9 | 0.74 | 1,318 false |
| | **blend** (= 10 m here) | 9.3 | +3.9 | 4.2 | 0.74 | 3 false |

### Wind direction (hours with station wind >= 10 km/h; mean circular difference)

| Station | 10 m | 700 hPa | blend |
|---|---:|---:|---:|
| Bosworth Upper | 60° | 65° | 64° |
| Tangle Ridge | 83° | 25° | 25° |
| Burstall Pass (225 h only) | 27° | 51° | 27° |

### Temperature (MAE)

| Station | 2 m | 700 hPa |
|---|---:|---:|
| Bosworth Upper | 2.7 °C | 2.2 °C |
| Tangle Ridge | 4.5 °C | 1.5 °C |
| Burstall Pass | 2.3 °C | 4.7 °C |

## Interpretation

- The height blend is the best or equal-best wind at all three stations. On
  the two ridge stations, 10 m model wind never reached 25 km/h while the
  stations did for 921 and 643 hours. At the sheltered Burstall Pass station,
  which sits below the model's ground, 700 hPa wind would be wildly too strong;
  the blend falls back to 10 m wind there by itself.
- Direction: the earlier provisional result (10 m direction better at
  Bosworth) did not hold on Bosworth's own cell (60° vs 65°, nearly equal) and
  is reversed at Tangle Ridge (83° vs 25°). The "hybrid" option (700 hPa
  speed, 10 m direction) has no support; the blend stays the default.
- The blend over-reads Tangle Ridge by about 7 km/h and flags many hours at
  25 km/h or more that the station did not see. A higher threshold or a
  station-specific correction could be tested later; the ranking is not
  sensitive to the threshold (see the research log).

## Earlier provisional result (superseded)

On 2026-11-18 Bosworth Upper was compared with the nearest stored cell 8.8 km
away, because the Open-Meteo daily limit had been reached. Those numbers
(blend MAE 7.2, 700 hPa MAE 8.2, 10 m MAE 17.6) pointed the same way and are
replaced by the table above.
