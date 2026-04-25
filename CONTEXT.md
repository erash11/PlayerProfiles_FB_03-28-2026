# Session Context

This file captures decisions, discoveries, and next steps from the initial build session (2026-03-28).

---

## What Was Built

A Python-based static HTML report generator. Run `generate_report.py` before a meeting, open the output HTML in a browser — no server required.

**Files created this session:**
- `generate_report.py` — CLI entry point
- `config.py` — absolute paths to all data sources
- `src/data.py` — data loading + joining via roster crosswalk
- `src/scorer.py` — TSA z→t scoring, domain composites, RAG
- `src/renderer.py` — Jinja2 template renderer
- `templates/report.html.j2` — self-contained HTML (dark theme, Chart.js, vanilla JS)
- `data/athlete_roster.csv` — crosswalk of 98 active athletes
- `requirements.txt` — duckdb, pandas, numpy, jinja2
- `tests/test_history.py`  — unit tests for history loaders, pop_stats, build_history

**Original spec (React + FastAPI) was replaced** in favor of a simpler static HTML generator. The spec files (TECH_SPEC.md, UI_WIREFRAMES.md, etc.) are still present for reference but no longer reflect the implementation.

---

## Data Sources (Actual Paths)

| Source | Path | Key Tables/Fields |
|--------|------|-------------------|
| ForcePlate | `C:/Users/eric_rash/Desktop/DEV/ForcePlate_DecisionSystem/data/forceplate.db` | `raw_tests`, `classified_athletes` |
| GPS | `C:/Users/eric_rash/Desktop/DEV/DataBase_GPS_Reporting/gps_report/data/gps_history.duckdb` | `athlete_sessions` |
| Body Weight | `C:/Users/eric_rash/Desktop/DEV/Football/BodWeightWeb/BodyWeightMaster.csv` | DATE, POS, NAME ("Last, First"), WEIGHT (lbs) |
| Roster | `data/athlete_roster.csv` | full_name, jersey_number, position, catapult_id, forcedecks_id |

---

## Athlete Roster Crosswalk

- **98 active athletes** (filtered to those with at least ForcePlate data)
- **83** have both Catapult (GPS) and ForceDecks IDs
- **15** have ForceDecks only — no Catapult ID (not yet set up in GPS system)
- Athletes on GPS only (no ForcePlate data) were excluded — no longer on active roster
- **Jersey numbers are mostly blank** (~15 populated). Fill manually in `data/athlete_roster.csv` for UI display.
- Name matching: GPS uses "First Last", ForcePlate uses "First Last", BW CSV uses "Last, First"

---

## TSA Scoring — 9 Axes, 5 Domains

| # | Axis | Domain | Source | Field |
|---|------|--------|--------|-------|
| 1 | Jump Height | CMJ | `raw_tests` | `"Jump Height (Imp-Mom)"` (cm) |
| 2 | Peak Power / BM | CMJ | `raw_tests` | `"Peak Power / BM"` (W/kg) |
| 3 | mRSI | CMJ | `classified_athletes` | `mrsi` |
| 4 | High Speed Distance | GPS | `athlete_sessions` | `high_speed_distance_m` (m, session avg) |
| 5 | Player Load | GPS | `athlete_sessions` | `total_player_load` (session avg) |
| 6 | Max Velocity | GPS | `athlete_sessions` | `max_velocity_ms` (m/s, session avg) |
| 7 | Body Weight | BW | `BodyWeightMaster.csv` | WEIGHT converted lbs → kg |
| 8 | Peak Force / BM | Strength | `imtp_tests` | `"Peak Vertical Force / BM"` (N/kg) |

**Display-only IMTP metrics** (in profile panel, not TSA): Peak Force N, RFD 0–100ms, RFD 0–200ms.

**Domain structure:** CMJ (axes 1–3), GPS (axes 4–6), BW (axis 7), Strength (axis 8), Weight Room (axis 9 — composite of up to 4 Perch exercises) — equal weight per available domain.
**TSA for athletes missing a domain:** computed as mean of available domains (noted in report). Weight Room is partial-data-tolerant: athletes with only some exercises still score.

---

## Known Data Gaps

- **38/98 athletes have no GPS data** in the 2025-09-01 to 2026-03-28 window — likely walk-ons, specialists, or players not yet set up in Catapult.
- **12/98 athletes had no body weight** in `BodyWeightMaster.csv` — fixed by BW fallback (2026-04-25): `_load_fd_bw()` pulls `"Bodyweight in Kilograms"` from ForceDecks `raw_tests` for these athletes. All 12 confirmed to have FD BW data.
- **98/98 athletes have IMTP data** in the 2025-09-01 to 2026-03-28 window (full coverage as of 2026-03-29).
- Body weight in CSV is in **pounds** and must be converted to kg (`* 0.453592`).
- `ForceDecks` also captures `"Bodyweight in Kilograms"` in `raw_tests` — could serve as BW fallback in a future version.

---

## Perch API Integration (pipeline verified and data ingested 2026-04-25)

Design decisions locked in brainstorming session (2026-04-23):

- **5th TSA domain: "Weight Room"** — sits alongside CMJ, GPS, BW, Strength
- **Exercises:** back squat, power clean, bench press, hang power clean
- **Metric:** 1RM computed as `weight / pct_1rm` per set from `/v3/sets`, normalized by bodyweight (1RM ÷ BW, both lbs)
- **Scoring:** 4 t-scores (one per exercise 1RM/BW) → Weight Room domain mean → TSA = mean of 5 domains
- **Radar:** Weight Room shows as a **single composite axis** (not 4 individual axes) → radar stays clean. Individual exercise 1RMs shown in profile panel only.
- **Athlete join:** name-match from Perch `/v2/users` endpoint → normalized name → `athlete_roster.csv`. Same `_normalize_name()` pattern as BW CSV.
- **Auth:** `Bearer` token in `.env` as `PERCH_API_TOKEN`. Copy `.env.example` → `.env`.
- **API pagination:** `/v2/users` and `/v3/sets` use `next_token`; ingest handles pagination.

### API details (confirmed 2026-04-25)

- **Base URL:** `https://api.perch.fit`
- **Auth scheme:** `Authorization: Bearer <token>` (not JWT despite API error message on first attempt)
- **Users:** `POST /v2/users` with `{"group_id": org_id}`. Org ID from `GET /v2/user` → `data.org_id` (Baylor = 959).
- **Sets/1RM:** `POST /v3/sets` with `{"group_id": 959, "exercise_id": <id>}`. Returns newest-first; stop paginating when `created_at < start_ts`. 1RM = `weight / pct_1rm` (pct_1rm is 0–1 decimal). Skip records where `pct_1rm` is null.
- **Exercise IDs:** Back Squat=1, Bench Press=2, Power Clean=19, Hang Power Clean=48 (in `_EXERCISE_ID_MAP`).
- **The `/stats` endpoint returns empty** for this org — do not use it.

### What was built (2026-04-24) — full implementation

**Ingest layer:**
- `config.py` — added `PERCH_DB` path (`data/perch.duckdb`)
- `requirements.txt` — added `requests>=2.31.0`, `python-dotenv>=1.0.0`
- `.env.example` — token template
- `src/perch_ingest.py` — full ingest script: `ensure_schema()`, `upsert_rows()`, `fetch_users()`, `fetch_sets_1rm()` (paginated per exercise), `ingest()`, CLI with `--start`/`--end`/`--probe`

**Data / scoring / rendering:**
- `src/data.py` — `load_perch()`, `load_perch_history()`, `_load_bw_lbs()`, updated `merge_all()`
- `src/scorer.py` — 4 Perch metrics in `_METRICS`, `_WEIGHT_ROOM_T`, `weight_room_domain`, 5-domain TSA, updated `missing_domains`
- `src/renderer.py` — 4 Perch z-columns, expanded `include_cols`, `build_history()` with `perch_hist` arg + perch loop, updated `render()` signature + `perch_count`
- `generate_report.py` — loads `perch_hist`, prints Perch coverage, passes to `render()`

**UI:**
- `templates/report.html.j2` — 9th radar axis ("Weight Room"), "Wt Rm" sortable table column, colspan 9→10, profile panel "Weight Room (Perch)" metrics section, TREND_DOMAIN_CFG + TREND_DETAIL_METRICS for wr, chart cleanup arrays updated, Perch coverage pill

**Tests:** 26 passing (18 in `test_perch.py` / `test_history.py` combined)

**Implementation plan:** `docs/superpowers/plans/2026-04-24-perch-weight-room-domain.md` (all 9 tasks complete)

### Ingest setup

```bash
cp .env.example .env                                            # fill in PERCH_API_TOKEN
python src/perch_ingest.py --probe                              # verify connectivity (no dates needed)
python src/perch_ingest.py --start 2025-09-01 --end 2026-03-28 # full ingest
# Weight Room domain activates automatically once data/perch.duckdb is populated
```

**Season ingest result (2026-04-25):** 436 athletes in org, 12,300 rows upserted across 4 exercises (Back Squat 16 pages, Bench Press 17 pages, Power Clean 29 pages, Hang Power Clean 2 pages). DB: `data/perch.duckdb`.

---

## BW Fallback (fully implemented 2026-04-25)

12 of 98 roster athletes had no match in `BodyWeightMaster.csv`, giving them NaN body weight. All 12 have `"Bodyweight in Kilograms"` recorded in ForceDecks `raw_tests`.

**Two private helpers added to `src/data.py`:**
- `_load_fd_bw(end_date)` — queries `raw_tests` for most recent `"Bodyweight in Kilograms"` per athlete on or before `end_date`. Returns `[forcedecks_id, weight_kg]`. Uses `test_date <= end_date` (no lower bound, matching `load_bodyweight` behavior). Catches all exceptions and returns empty DataFrame.
- `_load_bw_combined(start_date, end_date)` — coalesces CSV (primary) and FD (fallback). Returns `[name_normalized, weight_kg]`. CSV wins via `combine_first`; FD fills NaN gaps.

**Call sites updated:**
- `merge_all()` — replaced `load_bodyweight(end_date)` with `_load_bw_combined(start_date, end_date)`. BW domain score now works for all 12 athletes.
- `load_perch()` and `load_perch_history()` — after CSV BW join, applies FD fallback by `forcedecks_id`, converts kg→lbs, fills NaN `weight_lbs` before 1RM/BW division.

**Tests:** 8 new tests in `tests/test_perch.py`; total suite 34/34 passing.

**Implementation plan:** `docs/superpowers/plans/2026-04-24-bw-fallback.md`

---

## Known Issues / Future Improvements

1. **Jersey numbers blank** — fill `data/athlete_roster.csv` manually for UI display.
2. **15 FP-only athletes have no catapult_id** — add when they're set up in GPS system.
3. **BW fallback** — Fully implemented (2026-04-25). See `src/data.py`: `_load_fd_bw(end_date)`, `_load_bw_combined(start_date, end_date)`. Wired into `merge_all()`, `load_perch()`, `load_perch_history()`. 34/34 tests passing.
4. **Trend chart dual y-axes** — CMJ, GPS, and Strength detail charts show all metrics on a single y-axis. Metrics within Strength (N/kg vs N/s) have very different scales; add secondary y-axis in a future pass.
5. **Athlete comparison panel** — not yet implemented. Deferred.
6. **Position-specific normalization** — v1 uses full-roster z-scores. Position-specific norms are Phase 2.
7. **Report date range in UI** — currently set only via CLI args. A form inside the HTML for re-running was spec'd but not built.
8. **IMTP RFD in Strength domain** — currently only Peak Force/BM drives the Strength domain t-score. RFD 0–100ms and RFD 0–200ms are display-only. Consider adding them to the domain composite in a future version.

---

## ForcePlate Pipeline Notes

- Pipeline repo: `C:/Users/eric_rash/Desktop/DEV/ForcePlate_DecisionSystem`
- Metric names come from VALD ForceDecks API exactly as returned — see `config/thresholds.yaml` for full list
- Position normative thresholds (P25/P50/P75 per position) are in `config/thresholds.yaml` — not yet used in TSA but available for future position-specific scoring
- `classified_athletes` has pre-computed: `mrsi`, `ecc_peak_power_bm`, `asymmetry_pct`, `concentric_impulse`, `p1_impulse`, `p2_impulse` — richer data available for future axes
- **IMTP ingestion added 2026-03-29:** `imtp_tests` table in `forceplate.db` stores 4 metrics per test: `"Peak Vertical Force"`, `"Peak Vertical Force / BM"`, `"RFD - 100ms"`, `"RFD - 200ms"`. VALD API test_type string is `"IMTP"`. Config in `config/thresholds.yaml` under `imtp_test_type` and `imtp_target_metrics`.
- **To re-run IMTP ingestion:** `python -m src.ingest.pipeline --from 2025-09-01` from the ForcePlate_DecisionSystem directory (ingests both CMJ and IMTP in one pass).

## Pipeline Automation (2026-04-25)

- `C:/Users/eric_rash/Desktop/DEV/refresh_all_data.bat` — wrapper script that runs all three pipelines in sequence (ForcePlate → GPS → Perch) with per-step error reporting. Designed for Windows Task Scheduler (no `pause`).
- **GPS entry point:** `bulk_import.py` (imports data); `run_report.py` only generates reports from existing data.
- Season start hardcoded to `2025-09-01` at top of script — update each season.

## Downstream Projects

- **Risk_Stratification_Engine** (`C:/Users/eric_rash/Desktop/DEV/Risk_Stratification_Engine/`) reads the same canonical DB files via `config/paths.local.yaml` (already configured with correct paths). No copy needed — both projects read live files. `paths.example.yaml` is committed; `paths.local.yaml` is gitignored.

## GPS Pipeline Notes

- Pipeline repo: `C:/Users/eric_rash/Desktop/DEV/DataBase_GPS_Reporting`
- 513 total athletes in GPS DB; filtered to ~140 with sessions in 2025+; 98 in active roster
- Rich metrics available beyond what TSA uses: IMA counts, velocity bands, impact counts, accel/decel density

---

## Trend Charts (added 2026-03-30)
- All 4 domains have longitudinal charts in athlete profile panel
- Combined view: domain composite t-scores (0–100) over time
- Expandable per-domain detail: raw values on y-axis, t-score in hover tooltip
- GPS uses 7-day rolling average; null sentinels render off-season gaps as breaks
- T-scores in history use snapshot population stats for consistent baseline
