# Mountain Software

A public research project. It tests whether weather history, terrain from a
DEM, and dated human observations explain where wind loads snow and where it
scours it on Canadian Rockies peaks, better than a simple aspect-versus-wind
rule.

It is evidence synthesis and research. It does not decide whether anyone should climb anything.
Model output is never an official warning or a verified observation; for
avalanche conditions read the official
[Avalanche Canada forecast](https://avalanche.ca/forecasts).

- [`SPEC.md`](SPEC.md): project spec, decisions and acceptance checks
- [`CLAUDE.md`](CLAUDE.md): working rules
- [`docs/decisions.md`](docs/decisions.md): build decisions and why
- [`docs/weather-data.md`](docs/weather-data.md): what the weather APIs give, including issue-time limits
- [`docs/needs-from-mckinley.md`](docs/needs-from-mckinley.md): open questions
- [`docs/research-log/`](docs/research-log/): hypothesis, data, method, result, interpretation

## Setup

```bash
uv sync
uv run pytest
```

## Pipeline so far

```bash
uv run mountain routes load          # Module 1: GPX -> 250 m route points (SQLite)
uv run mountain weather cells        # Module 2: find the HRDPS cell of each route point
uv run mountain weather backfill     # Module 2: archive backfill (windows from the manifest)
uv run mountain weather collect      # Module 2: newest model run (the future daily job; not scheduled)
```

The database is `data/processed/mountain.sqlite` (git-ignored). Raw API
responses go to `data/raw/` (git-ignored).

## Data and licences

- Route tracks: see [`data/routes/manifest.toml`](data/routes/manifest.toml).
  Third-party GPX files are never committed.
- Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0, free
  tier is non-commercial), from Environment and Climate Change Canada's HRDPS
  model.
- DEM: NRCan MRDEM-30 (Open Government Licence - Canada 2.0). Contains
  modified Copernicus GLO-30 data.
