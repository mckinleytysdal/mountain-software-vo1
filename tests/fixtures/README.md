# Test fixtures

`openmeteo/*.json` are small real responses from Open-Meteo (GEM HRDPS
Continental), saved on 2026-11-18 so tests never need the internet.
Weather data by [Open-Meteo.com](https://open-meteo.com/), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Source model data:
Environment and Climate Change Canada (HRDPS).

The coordinates are cells near Lake Louise, not route tracks. No GPX file is
stored here; GPX tests build synthetic tracks in `tests/gpx_factory.py`.
