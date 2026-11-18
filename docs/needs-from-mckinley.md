# What Claude needs from McKinley

Only things Claude cannot do or decide alone. Newest at the bottom.

1. **The four GPX files.** Put them here, with these names (or edit `file` in
   `data/routes/manifest.toml`):
   - `data/routes/third_party/silverhorn_caltopo.gpx`
   - `data/routes/third_party/sir_douglas_west_ridge_trailamigo.gpx`
   - `data/routes/third_party/french_haig_robertson_alltrails.gpx`
   - `data/routes/own/north_victoria_2026-10-16_strava.gpx`

   The third-party and own folders are git-ignored, so the files stay on your
   computer. Then run `uv run pytest -m realdata` and
   `uv run mountain routes load`. If you would rather have Claude run it, upload
   the files in a chat with Claude; do not commit them.
2. **Strava privacy for North Victoria.** Is a privacy zone set on the
   activity, or should the first and last few hundred metres be trimmed before
   the file is committed? (Your site already shows this track publicly,
   simplified.)
3. **North Victoria summit height.** Claude switched the manifest to 3,388 m
   (north peak), not the 3,464 m in SPEC.md (south summit). Confirm.
4. **Track origins.** Source URLs for the three third-party tracks, and who
   recorded the Silverhorn CalTopo track (it is treated as third-party until
   you say otherwise).
