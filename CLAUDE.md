# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Football Player Performance Report** — a Python static HTML generator for Baylor Athletics' B.A.I.R. Initiative. Reads from three existing DuckDB pipelines, computes TSA (Total Score of Athleticism) composite scores, and renders a self-contained interactive HTML report.

**Run it:**
```bash
python generate_report.py --start 2025-09-01 --end 2026-03-28 --label "Spring 2026"
# Output: output/Spring_2026_2026-03-28.html
```

> The original React + FastAPI spec has been replaced by this approach. Reference specs are in `docs/` (TECH_SPEC.md, UI_WIREFRAMES.md, DATA_SCHEMA.md, TSA_METHODOLOGY.md) and do not reflect the implementation.

---

## Commands

```bash
pip install -r requirements.txt

# Generate a report for a date range
python generate_report.py --start YYYY-MM-DD --end YYYY-MM-DD --label "Label"

# Override output path
python generate_report.py --start 2025-09-01 --end 2026-03-28 --label "Spring 2026" --output out/custom.html

# Refresh all upstream pipelines (run before generating report)
# Wrapper script: C:/Users/eric_rash/Desktop/DEV/refresh_all_data.bat

# Individual pipeline updates:
# python C:/Users/eric_rash/Desktop/DEV/ForcePlate_DecisionSystem/src/ingest/pipeline.py
# cd C:/Users/eric_rash/Desktop/DEV/DataBase_GPS_Reporting/gps_report && python bulk_import.py --start 2025-09-01 --end <date>
# python src/perch_ingest.py --start 2025-09-01 --end <date>
```

---

## Architecture

```
generate_report.py      # CLI entry: argparse -> data -> score -> render -> write HTML
config.py               # absolute paths to all 5 data sources + output dir
src/
  data.py               # load_cmj(), load_gps(), load_bodyweight(), load_imtp(), load_perch(), merge_all()
  scorer.py             # z->t per metric, 5 domain composites, TSA, RAG
  renderer.py           # serialize DataFrame to JSON, render Jinja2 template
  perch_ingest.py       # Perch API client → data/perch.duckdb cache (run separately)
templates/
  report.html.j2        # dark-theme HTML: Chart.js radar (9 axes) + sortable table + inline JS
data/
  athlete_roster.csv    # 98 active athletes: full_name, jersey_number, position, catapult_id, forcedecks_id
  perch.duckdb          # Perch 1RM cache (not committed; populate with src/perch_ingest.py)
output/                 # generated HTML files (not committed)
```

## Data Sources

| Source | Path | Status |
|--------|------|--------|
| ForcePlate DB | `C:/Users/eric_rash/Desktop/DEV/ForcePlate_DecisionSystem/data/forceplate.db` | Built |
| GPS DB | `C:/Users/eric_rash/Desktop/DEV/DataBase_GPS_Reporting/gps_report/data/gps_history.duckdb` | Built |
| Body Weight CSV | `C:/Users/eric_rash/Desktop/DEV/Football/BodWeightWeb/BodyWeightMaster.csv` | Built |
| Roster crosswalk | `data/athlete_roster.csv` | Built |
| Perch DB | `data/perch.duckdb` (local cache, populated by `src/perch_ingest.py`) | **Built** |

**GPS pipeline note:** `bulk_import.py` imports data into the DB; `run_report.py` only generates reports from existing data — do not confuse them.

**ForcePlate DB tables used:** `raw_tests` (CMJ metrics), `classified_athletes` (mRSI + CMJ classification), `imtp_tests` (IMTP metrics). IMTP data is ingested via the ForcePlate pipeline (`ForcePlate_DecisionSystem/src/ingest/pipeline.py`).

**All paths are defined in `config.py`.** Change them there if pipelines move.

## TSA Scoring (9 axes, 5 domains)

| Domain | Metric | Source | Field |
|--------|--------|--------|-------|
| CMJ | Jump Height (cm) | `raw_tests` | `"Jump Height (Imp-Mom)"` |
| CMJ | Peak Power / BM (W/kg) | `raw_tests` | `"Peak Power / BM"` |
| CMJ | mRSI | `classified_athletes` | `mrsi` |
| GPS | High Speed Distance (m) | `athlete_sessions` | `high_speed_distance_m` |
| GPS | Player Load | `athlete_sessions` | `total_player_load` |
| GPS | Max Velocity (m/s) | `athlete_sessions` | `max_velocity_ms` |
| BW  | Body Weight (kg) | `BodyWeightMaster.csv` | WEIGHT x 0.453592 |
| Strength | Peak Force / BM (N/kg) | `imtp_tests` | `"Peak Vertical Force / BM"` |
| Weight Room | Back Squat 1RM/BW | `perch.duckdb` | 1RM (lbs) ÷ BW (lbs) |
| Weight Room | Power Clean 1RM/BW | `perch.duckdb` | 1RM (lbs) ÷ BW (lbs) |
| Weight Room | Bench Press 1RM/BW | `perch.duckdb` | 1RM (lbs) ÷ BW (lbs) |
| Weight Room | Hang Power Clean 1RM/BW | `perch.duckdb` | 1RM (lbs) ÷ BW (lbs) |

**Display-only IMTP metrics** (shown in profile panel, not in TSA domain score): Peak Force (N), RFD 0–100ms (N/s), RFD 0–200ms (N/s).

**Scoring:** z-score per metric (population = all athletes with that metric) -> t-score (z*10+50, clipped 0-100) -> domain mean (CMJ avg of 3, GPS avg of 3, BW = weight_t, Strength = peak_force_bm_t, Weight Room = mean of up to 4 exercise t-scores) -> TSA = mean of available domains (partial domain scores allowed for Weight Room).

**Weight Room radar axis:** single composite score (`weight_room_domain`); individual exercise 1RMs shown in profile panel only. Athletes without Perch data score from the remaining 4 domains; "Weight Room" shown in missing_domains note.

**RAG:** roster-relative -- top 33% green, middle 34% amber, bottom 33% red.

**Missing domain handling:** athletes missing any domain still get a TSA from available domains; a note appears in their profile panel.

## Perch API Integration (pipeline verified and data ingested 2026-04-25)

**API base:** `https://api.perch.fit` — Bearer token auth (`Authorization: Bearer <token>`).

**Ingest script:** `src/perch_ingest.py` — run before generating the report:
```bash
python src/perch_ingest.py --probe                              # verify connectivity (no dates needed)
python src/perch_ingest.py --start 2025-09-01 --end 2026-03-28 # full ingest
```

**Data source:** `POST /v3/sets` filtered by `exercise_id` — NOT `/stats` (which returns empty). 1RM is computed as `weight / pct_1rm` per set where `pct_1rm` is set (0–1 decimal). Records are newest-first; ingest stops paginating when `created_at` falls before `start_date`.

**Exercise IDs (confirmed):** Back Squat=1, Bench Press=2, Power Clean=19, Hang Power Clean=48. Defined in `_EXERCISE_ID_MAP` at top of `src/perch_ingest.py`.

**Users endpoint:** `POST /v2/users` with `{"group_id": org_id}`. Org ID resolved dynamically from `GET /v2/user` → `data.org_id` (Baylor = 959).

**Exercises tracked:** back squat, power clean, bench press, hang power clean.

**Metric:** 1RM computed from `weight / pct_1rm` per set, normalized by bodyweight (1RM ÷ BW, both lbs).

**Athlete join:** name-match from Perch `/v2/users` (first_name + last_name) to `athlete_roster.csv` full_name using `_normalize_name()`.

**API token:** stored in `.env` as `PERCH_API_TOKEN` (never committed). Copy `.env.example` → `.env` to get started.

## Athlete Roster

`data/athlete_roster.csv` is the join key between all three pipelines. **Do not delete it.**

- 98 active athletes; all have ForcePlate data
- 83 also have a Catapult GPS ID; 15 are not yet in Catapult
- Jersey numbers are mostly blank -- fill manually for UI display
- Joins: ForcePlate on `forcedecks_id`, GPS on `catapult_id`, BW on normalized `full_name`

To add new athletes or update IDs, edit `data/athlete_roster.csv` directly.

## What Is Not Yet Built

See [CONTEXT.md](CONTEXT.md) for full detail. Key deferred items:

- **Perch / Weight Room domain** -- Fully implemented (2026-04-24). Run `src/perch_ingest.py --probe` first time to verify API field names, then full ingest. Once `data/perch.duckdb` is populated the Weight Room domain activates automatically.
- **Dual y-axes in trend detail charts** -- RFD (N/s) and Peak Force/BM (N/kg) share a single y-axis; add secondary axis when Chart.js dual-axis is wired up
- **Athlete comparison panel** -- side-by-side spider chart overlay
- **BW fallback** -- Fully implemented (2026-04-25). `_load_fd_bw()` and `_load_bw_combined()` in `src/data.py` fill gaps using `"Bodyweight in Kilograms"` from `raw_tests`. CSV wins; FD fills NaN. Wired into `merge_all()`, `load_perch()`, `load_perch_history()`.
- **Position-specific normalization** -- v1 uses full-roster z-scores
- **Jersey numbers** -- need manual entry in `data/athlete_roster.csv`

## Downstream Projects

**Risk_Stratification_Engine** (`C:/Users/eric_rash/Desktop/DEV/Risk_Stratification_Engine/`) reads the same canonical DB files. Its `config/paths.local.yaml` already points to the correct paths. Run `refresh_all_data.bat` to update data for both projects simultaneously.

## Git Conventions

- Branches: `main` (stable) -> `dev` (active) -> `feature/*`
- Commit prefixes: `feat:`, `fix:`, `refactor:`, `data:`, `docs:`
- `.gitignore` excludes: `__pycache__/`, `venv/`, `.env`, `data/*.duckdb`, `data/raw/`
