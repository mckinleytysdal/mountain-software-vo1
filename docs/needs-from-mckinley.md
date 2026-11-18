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
5. **Review the 77 draft observations** in
   `data/observations/trip_reports_draft.toml`. They come word for word from
   your trip reports. For each one: fix anything wrong, add `wind_effect`
   (loaded / scoured / none_seen) where you remember it, add lat/lon if your
   original photos or tracks have them, then set `needs_review = false`.
6. **New field entries.** Use `templates/field_observation.toml` on your next
   trips, with `wind_effect` filled in. These are the labels the research
   question needs.

## Answered 2026-11-18

- 1: GPX files received; real-data checks pass (see decisions D45).
- 2: North Victoria committed untrimmed.
- 3: 3,388 m confirmed.
- 4: origins unknown; treated as third-party tracks.
- 5: the review is not needed. Future field entries with the template are what count.
