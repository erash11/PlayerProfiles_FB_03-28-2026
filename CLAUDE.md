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
```

---

## Architecture

```
generate_report.py      # CLI entry: argparse -> data -> score -> render -> write HTML
config.py               # absolute paths to all 4 data sources + output dir
src/
  data.py               # load_cmj(), load_gps(), load_bodyweight(), load_imtp(), merge_all()
  scorer.py             # z->t per metric, domain composites, TSA, RAG
  renderer.py           # serialize DataFrame to JSON, render Jinja2 template
templates/
  report.html.j2        # dark-theme HTML: Chart.js radar (8 axes) + sortable table + inline JS
data/
  athlete_roster.csv    # 98 active athletes: full_name, jersey_number, position, catapult_id, forcedecks_id
output/                 # generated HTML files (not committed)
```

## Data Sources

| Source | Path | Status |
|--------|------|--------|
| ForcePlate DB | `C:/Users/eric_rash/Desktop/DEV/ForcePlate_DecisionSystem/data/forceplate.db` | Built |
| GPS DB | `C:/Users/eric_rash/Desktop/DEV/DataBase_GPS_Reporting/gps_report/data/gps_history.duckdb` | Built |
| Body Weight CSV | `C:/Users/eric_rash/Desktop/DEV/Football/BodWeightWeb/BodyWeightMaster.csv` | Built |
| Roster crosswalk | `data/athlete_roster.csv` | Built |
| Perch DB | `data/perch.duckdb` (local cache, populated by `src/perch_ingest.py`) | **Planned** |

**ForcePlate DB tables used:** `raw_tests` (CMJ metrics), `classified_athletes` (mRSI + CMJ classification), `imtp_tests` (IMTP metrics). IMTP data is ingested via the ForcePlate pipeline (`ForcePlate_DecisionSystem/src/ingest/pipeline.py`).

**All paths are defined in `config.py`.** Change them there if pipelines move.

## TSA Scoring (current: 8 axes, 4 domains; planned: +1 domain)

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
| **Weight Room** *(planned)* | Back Squat 1RM/BW | Perch API → `perch.duckdb` | 1RM (lbs) ÷ BW (lbs) |
| **Weight Room** *(planned)* | Power Clean 1RM/BW | Perch API → `perch.duckdb` | 1RM (lbs) ÷ BW (lbs) |
| **Weight Room** *(planned)* | Bench Press 1RM/BW | Perch API → `perch.duckdb` | 1RM (lbs) ÷ BW (lbs) |
| **Weight Room** *(planned)* | Hang Power Clean 1RM/BW | Perch API → `perch.duckdb` | 1RM (lbs) ÷ BW (lbs) |

**Display-only IMTP metrics** (shown in profile panel, not in TSA domain score): Peak Force (N), RFD 0–100ms (N/s), RFD 0–200ms (N/s).

**Scoring:** z-score per metric (population = all athletes with that metric) -> t-score (z*10+50, clipped 0-100) -> domain mean (CMJ avg of 3, GPS avg of 3, BW = weight_t, Strength = peak_force_bm_t) -> TSA = mean of available domains.

**Planned Weight Room scoring:** 4 t-scores (one per exercise 1RM/BW) -> Weight Room domain mean -> TSA becomes mean of 5 domains. Weight Room shows as a single composite axis on the radar; individual exercise 1RMs displayed in profile panel only.

**RAG:** roster-relative -- top 33% green, middle 34% amber, bottom 33% red.

**Missing domain handling:** athletes missing any domain still get a TSA from available domains; a note appears in their profile panel.

## Perch API Integration (Planned — design complete, implementation pending)

**API:** Bearer token auth. Docs at `https://app.swaggerhub.com/apis-docs/PerchFitness/perch-api/1.2.0`

**Ingest strategy:** `src/perch_ingest.py` calls `/v2/users` to build name→perch_id mapping, then `/stats` endpoint to pull 1RM per exercise per athlete. Caches to `data/perch.duckdb`. Run separately before generating report.

**Exercises tracked:** back squat, power clean, bench press, hang power clean.

**Metric:** 1RM (from Perch `/stats` ONE_RM field), normalized by bodyweight (1RM ÷ BW, both in lbs).

**Athlete join:** name-match from Perch `/v2/users` (first_name + last_name) to `athlete_roster.csv` full_name using same `_normalize_name()` pattern as BW CSV join.

**API token:** stored in `.env` as `PERCH_API_TOKEN` (never committed).

## Athlete Roster

`data/athlete_roster.csv` is the join key between all three pipelines. **Do not delete it.**

- 98 active athletes; all have ForcePlate data
- 83 also have a Catapult GPS ID; 15 are not yet in Catapult
- Jersey numbers are mostly blank -- fill manually for UI display
- Joins: ForcePlate on `forcedecks_id`, GPS on `catapult_id`, BW on normalized `full_name`

To add new athletes or update IDs, edit `data/athlete_roster.csv` directly.

## What Is Not Yet Built

See [CONTEXT.md](CONTEXT.md) for full detail. Key deferred items:

- **Perch / Weight Room domain** -- `src/perch_ingest.py`, `data/perch.duckdb`, 5th TSA domain. Design complete (2026-04-23), implementation pending.
- **Dual y-axes in trend detail charts** -- RFD (N/s) and Peak Force/BM (N/kg) share a single y-axis; add secondary axis when Chart.js dual-axis is wired up
- **Athlete comparison panel** -- side-by-side spider chart overlay
- **BW fallback** -- use `"Bodyweight in Kilograms"` from ForceDecks `raw_tests` when CSV has no match
- **Position-specific normalization** -- v1 uses full-roster z-scores
- **Jersey numbers** -- need manual entry in `data/athlete_roster.csv`

## Git Conventions

- Branches: `main` (stable) -> `dev` (active) -> `feature/*`
- Commit prefixes: `feat:`, `fix:`, `refactor:`, `data:`, `docs:`
- `.gitignore` excludes: `__pycache__/`, `venv/`, `.env`, `data/*.duckdb`, `data/raw/`
