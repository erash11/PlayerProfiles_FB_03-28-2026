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

## TSA Scoring — 7 Axes (Confirmed)

| # | Axis | Source | Field |
|---|------|--------|-------|
| 1 | Jump Height | `raw_tests` | `"Jump Height (Imp-Mom)"` (cm) |
| 2 | Peak Power / BM | `raw_tests` | `"Peak Power / BM"` (W/kg) |
| 3 | mRSI | `classified_athletes` | `mrsi` |
| 4 | High Speed Distance | `athlete_sessions` | `high_speed_distance_m` (m, session avg) |
| 5 | Player Load | `athlete_sessions` | `total_player_load` (session avg) |
| 6 | Max Velocity | `athlete_sessions` | `max_velocity_ms` (m/s, session avg) |
| 7 | Body Weight | `BodyWeightMaster.csv` | WEIGHT converted lbs → kg |

**Domain structure:** CMJ (axes 1–3), GPS (axes 4–6), BW (axis 7) — equal 33% weight each.
**TSA for athletes missing a domain:** computed as mean of available domains (noted in report).

---

## Known Data Gaps

- **38/98 athletes have no GPS data** in the 2025-09-01 to 2026-03-28 window — likely walk-ons, specialists, or players not yet set up in Catapult.
- **12/98 athletes have no body weight** in `BodyWeightMaster.csv` — name matching or data gaps.
- Body weight in CSV is in **pounds** and must be converted to kg (`* 0.453592`).
- `ForceDecks` also captures `"Bodyweight in Kilograms"` in `raw_tests` — could serve as BW fallback in a future version.

---

## Known Issues / Future Improvements

1. **Jersey numbers blank** — fill `data/athlete_roster.csv` manually for UI display.
2. **15 FP-only athletes have no catapult_id** — add when they're set up in GPS system.
3. **BW fallback** — could use `"Bodyweight in Kilograms"` from ForceDecks `raw_tests` when CSV has no match.
4. **Trend charts** not yet implemented — spec calls for longitudinal CMJ/GPS/BW line charts on the athlete profile. Deferred to next session.
5. **Athlete comparison panel** — not yet implemented. Deferred.
6. **Position-specific normalization** — v1 uses full-roster z-scores. Position-specific norms are Phase 2.
7. **Report date range in UI** — currently set only via CLI args. A form inside the HTML for re-running was spec'd but not built.

---

## ForcePlate Pipeline Notes

- Pipeline repo: `C:/Users/eric_rash/Desktop/DEV/ForcePlate_DecisionSystem`
- Metric names come from VALD ForceDecks API exactly as returned — see `config/thresholds.yaml` for full list
- Position normative thresholds (P25/P50/P75 per position) are in `config/thresholds.yaml` — not yet used in TSA but available for future position-specific scoring
- `classified_athletes` has pre-computed: `mrsi`, `ecc_peak_power_bm`, `asymmetry_pct`, `concentric_impulse`, `p1_impulse`, `p2_impulse` — richer data available for future axes

## GPS Pipeline Notes

- Pipeline repo: `C:/Users/eric_rash/Desktop/DEV/DataBase_GPS_Reporting`
- 513 total athletes in GPS DB; filtered to ~140 with sessions in 2025+; 98 in active roster
- Rich metrics available beyond what TSA uses: IMA counts, velocity bands, impact counts, accel/decel density
