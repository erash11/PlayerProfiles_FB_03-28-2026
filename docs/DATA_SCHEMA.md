# Football Player Performance Report
## Data Schema

**Version:** 1.0
**Created:** March 2026
**Status:** Foundation — to be refined with pipeline documentation

---

## 1. Overview

This schema is a starting foundation. It will be updated once the Claude.md and pipeline
documentation files from the CMJ, GPS, and body weight projects are provided. Fields, data
types, and table relationships may change to match actual pipeline output formats.

**Database:** DuckDB (preferred)
**Design principle:** Flexible enough to accommodate changes without major refactoring.

---

## 2. Core Tables

### athletes

Stores basic roster information.

```sql
CREATE TABLE athletes (
    athlete_id    INTEGER PRIMARY KEY,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    jersey_number INTEGER,
    position      TEXT NOT NULL,
    -- QB, RB, WR, TE, OL, DL, LB, DB, ST, K, P
    class_year    TEXT,
    -- FR, SO, JR, SR
    active        BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Notes:
- athlete_id should match whatever ID is used in existing pipelines if possible
- active flag allows soft-deletes without data loss
- Position values should be standardized across all tables

---

### cmj_tests

Individual CMJ test results from ForceDecks or VALD.

```sql
CREATE TABLE cmj_tests (
    cmj_id                   INTEGER PRIMARY KEY,
    athlete_id               INTEGER NOT NULL REFERENCES athletes(athlete_id),
    test_date                TIMESTAMP NOT NULL,
    jump_height_cm           REAL,
    peak_force_n             REAL,
    peak_power_w             REAL,
    reactive_strength_index  REAL,
    contraction_time_ms      REAL,
    flight_time_ms           REAL,
    takeoff_velocity_ms      REAL,
    impulse_ns               REAL,
    left_right_asymmetry_pct REAL,
    notes                    TEXT,
    data_source              TEXT,
    -- e.g., 'ForceDecks', 'VALD'
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Notes:
- Field names and units are placeholders — update to match actual ForceDecks export columns
- Multiple tests per session are possible; each row = one attempt
- left_right_asymmetry_pct is optional — include if available from your pipeline

---

### gps_sessions

Session-level GPS and external load data from Catapult.

```sql
CREATE TABLE gps_sessions (
    gps_id                INTEGER PRIMARY KEY,
    athlete_id            INTEGER NOT NULL REFERENCES athletes(athlete_id),
    session_date          TIMESTAMP NOT NULL,
    session_type          TEXT,
    -- 'practice', 'game', 'conditioning', 'walkthrough'
    total_distance_m      REAL,
    high_speed_dist_m     REAL,
    -- typically > 5.5 m/s threshold
    sprint_dist_m         REAL,
    -- typically > 7.0 m/s threshold
    sprint_count          INTEGER,
    accel_count           INTEGER,
    decel_count           INTEGER,
    player_load           REAL,
    -- Catapult proprietary metric
    max_velocity_ms       REAL,
    avg_metabolic_power   REAL,
    duration_minutes      REAL,
    notes                 TEXT,
    data_source           TEXT,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Notes:
- Field names will be reconciled with actual Catapult API output when pipeline docs are provided
- Document the speed thresholds used in your setup (high-speed zone, sprint zone)
- session_type matters for filtering — do not average games and walkthroughs together

---

### body_weight

Body weight and composition measurements.

```sql
CREATE TABLE body_weight (
    bw_id              INTEGER PRIMARY KEY,
    athlete_id         INTEGER NOT NULL REFERENCES athletes(athlete_id),
    measurement_date   TIMESTAMP NOT NULL,
    weight_kg          REAL NOT NULL,
    body_fat_pct       REAL,
    lean_mass_kg       REAL,
    fat_mass_kg        REAL,
    measurement_method TEXT,
    -- 'scale', 'DXA', 'InBody'
    notes              TEXT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Notes:
- weight_kg is the only required field beyond FK and date
- measurement_method matters for longitudinal trends — do not silently mix DXA and scale values
- Schema assumes kg; convert if pipeline outputs lbs

---

### tsa_scores

Computed TSA scores per athlete per reporting period. Populated by tsa_scorer.py.

```sql
CREATE TABLE tsa_scores (
    score_id            INTEGER PRIMARY KEY,
    athlete_id          INTEGER NOT NULL REFERENCES athletes(athlete_id),
    report_period_start DATE NOT NULL,
    report_period_end   DATE NOT NULL,
    report_label        TEXT,
    -- e.g., 'Spring 2026', 'Post-Summer 2026'

    -- Domain z-scores
    cmj_z               REAL,
    gps_z               REAL,
    bodyweight_z        REAL,

    -- Domain t-scores
    cmj_t               REAL,
    gps_t               REAL,
    bodyweight_t        REAL,

    -- Composite
    tsa_composite       REAL,
    tsa_rank            INTEGER,
    rag_status          TEXT,
    -- 'green', 'amber', 'red'

    generated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Notes:
- One row per athlete per reporting period
- Regenerating a report for the same period should UPDATE, not duplicate
- RAG thresholds: top 33% = green, middle 34% = amber, bottom 33% = red
- tsa_rank is relative to the roster included in that report run

---

### report_runs

Audit trail of when reports were generated and with what parameters.

```sql
CREATE TABLE report_runs (
    run_id         INTEGER PRIMARY KEY,
    report_label   TEXT,
    period_start   DATE NOT NULL,
    period_end     DATE NOT NULL,
    athletes_count INTEGER,
    generated_by   TEXT,
    generated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes          TEXT
);
```

---

## 3. Relationships

```
athletes -+--- cmj_tests       (one athlete, many CMJ tests)
           +--- gps_sessions    (one athlete, many GPS sessions)
           +--- body_weight     (one athlete, many measurements)
           +--- tsa_scores      (one athlete, many scoring periods)
```

---

## 4. Key Data Assumptions (Pending Pipeline Docs)

**CMJ**
- ForceDecks exports one row per test attempt
- Test date/time is included in the export
- Athlete identified by name or ID that maps to the athletes table

**GPS**
- Catapult API or CSV export provides session summaries, not raw per-second data
- Each row = one athlete, one session
- session_type either present in export or inferred from existing pipeline logic

**Body Weight**
- Units assumed to be kg — convert on import if pipeline uses lbs

---

## 5. TODO — Pending Pipeline Documentation

- [ ] Confirm exact column names from ForceDecks export for cmj_tests
- [ ] Confirm exact column names from Catapult API output for gps_sessions
- [ ] Confirm body weight pipeline source and field names
- [ ] Confirm athlete ID matching strategy across all three pipelines
- [ ] Confirm measurement units for all fields
- [ ] Confirm GPS speed thresholds for high-speed and sprint zones
- [ ] Determine whether DXA body composition data should be integrated

---
*Update this document when pipeline docs are provided. Schema is intentionally flexible.*
