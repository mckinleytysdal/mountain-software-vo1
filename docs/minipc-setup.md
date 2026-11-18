# Mini PC: running the daily collector (not switched on)

Nothing here is installed or scheduled. These are the steps for when the Mini
PC exists.

1. Install `uv`, clone this repo, then run:

   ```bash
   uv sync
   uv run pytest
   ```
2. Put the GPX files in place (see `docs/needs-from-mckinley.md`), then run:

   ```bash
   uv run mountain routes load
   uv run mountain weather cells
   uv run mountain weather backfill
   ```
3. Try one collection by hand:

   ```bash
   uv run mountain weather collect
   ```

   It stores the newest published HRDPS run for every cell. Running it twice
   adds no rows and makes no extra API calls.
4. Schedule it about every 6 hours (HRDPS runs at 00, 06, 12 and 18 UTC and
   is published 1-3 h later). For example, a systemd timer:

   `~/.config/systemd/user/mountain-collect.service`

   ```ini
   [Unit]
   Description=Mountain Software: collect newest HRDPS run

   [Service]
   Type=oneshot
   WorkingDirectory=%h/mountain-software-vo1
   ExecStart=%h/.local/bin/uv run mountain weather collect
   ```

   `~/.config/systemd/user/mountain-collect.timer`

   ```ini
   [Unit]
   Description=Run the collector 4 times a day

   [Timer]
   OnCalendar=*-*-* 03,09,15,21:20:00 UTC
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```

   Turn it on only when ready:

   ```bash
   systemctl --user enable --now mountain-collect.timer
   ```
5. Back up `data/processed/mountain.sqlite` and `data/raw/`. Neither is in git.

Notes:
- Free Open-Meteo use is non-commercial, with limits of 10,000 calls a day
  and 5,000 an hour. Four runs a day for about 15 cells is about 60 calls a day.
- If a run is missed, `weather backfill --start <date>` fills it from the
  archive later, with true issue times for dates from 2026-04-02 on.
