# CLAUDE.md: Mountain Software

Read `SPEC.md` first. It holds the project spec, decisions, route facts, and acceptance checks. This file holds the working rules.

## What this project is

A public research and resume project. It tests whether weather history, terrain from a DEM, and dated human observations explain where wind loads snow and where it scours it on Canadian Rockies peaks, better than a simple aspect-versus-wind rule. It is evidence synthesis, not a source of safety decisions.

## How to work with McKinley

McKinley is learning Python and wants to understand every line, not only run it. After each module:

1. Stop building.
2. Teach the module in easy words, with climbing or weather analogies. Define every new term once.
3. Walk through each important function with a small worked example.
4. Run the tests and explain what each one proves and what it does not prove.
5. List anything you could not check or had to assume.
6. Quiz McKinley with 3 to 5 questions, one at a time, in plain words. If an answer is wrong, explain and ask a differently worded question.
7. Write a short note in `docs/learning-log/` with the module name, date, what was explained, and how the quiz went.
8. Wait. Start the next module only after McKinley passes and says to continue.

Decisions are already made in `SPEC.md`. Do not run a long new interview. Ask only when blocked, and ask one question at a time.

## Hard wording rules

- Call the output "relative exposure to potential wind loading", never a hazard rating.
- Never write safe, unsafe, go, or no-go in any output, label, or comment.
- Every output shows evidence, data age, uncertainty, and a link to the official Avalanche Canada bulletin.
- Do not use a colour scale that looks like the 5-level avalanche danger scale.
- A model output is never an official warning or a verified observation.

## Data rules

- The repo is public. Third-party GPX files (Trail Amigo, AllTrails, CalTopo) are never committed and never copied into docs or tests. Keep them in a git-ignored folder.
- The only committed track is McKinley's own North Victoria Strava export. Before committing it, confirm Strava privacy zones or trimmed ends with McKinley.
- Commit a manifest of every track: source, download date, terms note.
- Raw weather API responses stay in git-ignored `data/raw/`.
- For other people's reports and photos, store link, date, author, and extracted facts, never copies.
- Glacier tracks are reference geometry, not safe lines.

## Engineering rules

- Python with `uv` and `pyproject.toml`. SQLite for the database. `pytest` for tests. Use `uv run pytest` and `uv run` for scripts.
- Conventional package layout, with tests alongside the code. Keep raw and processed data in separate folders. Create a folder only when a component needs it.
- Store all times in UTC. Store forecast issue time and valid time as separate fields.
- Every derived value records its method version.
- Keep raw API responses. Keep observation date separate from publication date.
- Collectors must be safe to rerun: no duplicate rows.
- Tests never use the live internet. Use saved sample responses.
- Use DEM elevation for terrain work, not GPX elevation.
- No multi-agent orchestration and no vector database in Prototype 0.

## Honesty rules

- Do not say something works until you have run it. Show what you ran.
- Say plainly what you could not verify, and what you assumed.
- Document failed approaches and failed hypotheses.
- Report results as exploratory, with uncertainty.

## Scope guard

Only build what the current module needs. Out of scope for Prototype 0: full snowpack physics, route-level avalanche forecasting, autonomous warnings, Facebook scraping, time-decay estimation, Bayesian updating, kriging, the website agent, and commercial use.
