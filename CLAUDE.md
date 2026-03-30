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

| Source | Path |
|--------|------|
| ForcePlate DB | `C:/Users/eric_rash/Desktop/DEV/ForcePlate_DecisionSystem/data/forceplate.db` |
| GPS DB | `C:/Users/eric_rash/Desktop/DEV/DataBase_GPS_Reporting/gps_report/data/gps_history.duckdb` |
| Body Weight CSV | `C:/Users/eric_rash/Desktop/DEV/Football/BodWeightWeb/BodyWeightMaster.csv` |
| Roster crosswalk | `data/athlete_roster.csv` |

**ForcePlate DB tables used:** `raw_tests` (CMJ metrics), `classified_athletes` (mRSI + CMJ classification), `imtp_tests` (IMTP metrics). IMTP data is ingested via the ForcePlate pipeline (`ForcePlate_DecisionSystem/src/ingest/pipeline.py`).

**All paths are defined in `config.py`.** Change them there if pipelines move.

## TSA Scoring (8 axes, 4 domains)

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

**Display-only IMTP metrics** (shown in profile panel, not in TSA domain score): Peak Force (N), RFD 0–100ms (N/s), RFD 0–200ms (N/s).

**Scoring:** z-score per metric (population = all athletes with that metric) -> t-score (z*10+50, clipped 0-100) -> domain mean (CMJ avg of 3, GPS avg of 3, BW = weight_t, Strength = peak_force_bm_t) -> TSA = mean of available domains.

**RAG:** roster-relative -- top 33% green, middle 34% amber, bottom 33% red.

**Missing domain handling:** athletes missing any domain still get a TSA from available domains; a note appears in their profile panel.

## Athlete Roster

`data/athlete_roster.csv` is the join key between all three pipelines. **Do not delete it.**

- 98 active athletes; all have ForcePlate data
- 83 also have a Catapult GPS ID; 15 are not yet in Catapult
- Jersey numbers are mostly blank -- fill manually for UI display
- Joins: ForcePlate on `forcedecks_id`, GPS on `catapult_id`, BW on normalized `full_name`

To add new athletes or update IDs, edit `data/athlete_roster.csv` directly.

## What Is Not Yet Built

See [CONTEXT.md](CONTEXT.md) for full detail. Key deferred items:

- **Trend charts** -- longitudinal CMJ/GPS/BW line charts on athlete profile
- **Athlete comparison panel** -- side-by-side spider chart overlay
- **BW fallback** -- use `"Bodyweight in Kilograms"` from ForceDecks `raw_tests` when CSV has no match
- **Position-specific normalization** -- v1 uses full-roster z-scores
- **Jersey numbers** -- need manual entry in `data/athlete_roster.csv`

## Git Conventions

- Branches: `main` (stable) -> `dev` (active) -> `feature/*`
- Commit prefixes: `feat:`, `fix:`, `refactor:`, `data:`, `docs:`
- `.gitignore` excludes: `__pycache__/`, `venv/`, `.env`, `data/*.duckdb`, `data/raw/`
