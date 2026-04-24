# Perch Weight Room Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fifth TSA domain — "Weight Room" — by ingesting Perch VBT 1RM data into a local DuckDB cache, scoring it alongside CMJ/GPS/BW/Strength, and surfacing the composite on the radar chart and per-exercise detail in the profile panel.

**Architecture:** `src/perch_ingest.py` is a standalone CLI that calls the Perch REST API, normalizes athlete names, and upserts 1RM records into `data/perch.duckdb`. `src/data.py` reads that cache and joins normalized 1RM/BW ratios onto the roster, exactly like the existing IMTP/GPS loaders. `src/scorer.py` adds a `weight_room_domain` column; `src/renderer.py` and `templates/report.html.j2` surface the 5th axis and the per-exercise profile panel section.

**Tech Stack:** Python 3.11+, DuckDB 1.x, pandas, requests, python-dotenv (new), Jinja2, Chart.js (existing)

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `config.py` | Add `PERCH_DB` path |
| Modify | `requirements.txt` | Add `requests>=2.31.0`, `python-dotenv>=1.0.0` |
| Create | `.env.example` | Token template |
| Create | `src/perch_ingest.py` | Full API client + DuckDB upsert + CLI |
| Modify | `src/data.py` | Add `load_perch()`, `load_perch_history()`, update `merge_all()` |
| Modify | `src/scorer.py` | 4 new metrics, `_WEIGHT_ROOM_T`, `weight_room_domain`, 5-domain TSA |
| Modify | `src/renderer.py` | 4 new z-columns, `include_cols`, `build_history()` signature + loop, `render()` |
| Modify | `generate_report.py` | Load `perch_hist`, print coverage, pass to `render()` |
| Modify | `templates/report.html.j2` | 9th spider axis, Weight Room table column, profile section, trend chart |
| Create | `tests/test_perch.py` | Unit tests for ingest schema/upsert and scorer/renderer perch paths |
| Modify | `tests/test_history.py` | Extend `_make_df()` + `pop_stats` + `build_history` tests for 5-domain world |

---

## Task 1: Bootstrap — config, requirements, .env.example

**Files:**
- Modify: `config.py`
- Modify: `requirements.txt`
- Create: `.env.example`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_perch.py`:

```python
"""Tests for Perch ingest and Weight Room domain."""
import os
import tempfile
import pytest
import duckdb
import pandas as pd


def test_perch_db_config_exists():
    """PERCH_DB must be importable from config."""
    from config import PERCH_DB
    assert PERCH_DB is not None
    assert str(PERCH_DB).endswith("perch.duckdb")
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_perch.py::test_perch_db_config_exists -v
```
Expected: `ImportError: cannot import name 'PERCH_DB'`

- [ ] **Step 3: Add PERCH_DB to config.py**

Open `config.py` and add after the `ROSTER_CSV` line:

```python
PERCH_DB = PROJECT_ROOT / "data" / "perch.duckdb"
```

- [ ] **Step 4: Add dependencies to requirements.txt**

Replace contents with:

```
duckdb>=1.0.0
pandas>=2.0.0
numpy>=1.26.0
jinja2>=3.1.0
requests>=2.31.0
python-dotenv>=1.0.0
```

- [ ] **Step 5: Create .env.example**

```
PERCH_API_TOKEN=your_perch_bearer_token_here
```

- [ ] **Step 6: Run test to verify it passes**

```
pytest tests/test_perch.py::test_perch_db_config_exists -v
```
Expected: PASS

- [ ] **Step 7: Install new deps**

```
pip install requests python-dotenv
```

- [ ] **Step 8: Commit**

```bash
git add config.py requirements.txt .env.example tests/test_perch.py
git commit -m "feat: bootstrap Perch integration — config path, deps, env template"
```

---

## Task 2: Perch ingest — DB schema and upsert (no HTTP)

**Files:**
- Create: `src/perch_ingest.py` (schema + upsert only, no HTTP yet)
- Modify: `tests/test_perch.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_perch.py`:

```python
def test_ensure_schema_creates_table():
    """ensure_schema() creates perch_1rm with correct columns."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        tmp = f.name
    try:
        conn = duckdb.connect(tmp)
        from src.perch_ingest import ensure_schema
        ensure_schema(conn)
        cols = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='perch_1rm'").df()
        col_names = set(cols["column_name"].tolist())
        conn.close()
        assert {"name_normalized", "perch_user_id", "exercise", "one_rm_lbs", "test_date"} <= col_names
    finally:
        os.unlink(tmp)


def test_upsert_rows_inserts_and_deduplicates():
    """upsert_rows() handles duplicate (name, exercise, date) by keeping latest."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        tmp = f.name
    try:
        conn = duckdb.connect(tmp)
        from src.perch_ingest import ensure_schema, upsert_rows
        ensure_schema(conn)

        rows = [
            {"name_normalized": "alice smith", "perch_user_id": "u1",
             "exercise": "Back Squat", "one_rm_lbs": 315.0, "test_date": "2025-10-01"},
            {"name_normalized": "alice smith", "perch_user_id": "u1",
             "exercise": "Back Squat", "one_rm_lbs": 320.0, "test_date": "2025-10-01"},  # same key
            {"name_normalized": "bob jones",  "perch_user_id": "u2",
             "exercise": "Bench Press",  "one_rm_lbs": 225.0, "test_date": "2025-10-01"},
        ]
        upsert_rows(conn, rows)

        count = conn.execute("SELECT COUNT(*) FROM perch_1rm").fetchone()[0]
        alice_1rm = conn.execute(
            "SELECT one_rm_lbs FROM perch_1rm WHERE name_normalized='alice smith'"
        ).fetchone()[0]
        conn.close()

        assert count == 2, f"Expected 2 rows (deduped), got {count}"
        assert alice_1rm == pytest.approx(320.0), "Later value should overwrite earlier"
    finally:
        os.unlink(tmp)
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_perch.py::test_ensure_schema_creates_table tests/test_perch.py::test_upsert_rows_inserts_and_deduplicates -v
```
Expected: `ModuleNotFoundError: No module named 'src.perch_ingest'`

- [ ] **Step 3: Create src/perch_ingest.py with schema + upsert**

```python
"""Perch API ingest → data/perch.duckdb local cache.

Run this before generating the report:
    python src/perch_ingest.py --start 2025-09-01 --end 2026-03-28

⚠  VERIFY BEFORE FIRST RUN — Perch API field names are based on the design doc.
   Use --probe to dump a raw /stats response and confirm field names match
   the constants defined in the _API section below.
"""

import argparse
import os
import re
import sys
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

# Allow running as a script from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PERCH_DB

load_dotenv()

# ── Perch API constants ──────────────────────────────────────────────────────
# ⚠ Verify these against the live API. Use --probe to inspect raw responses.

PERCH_API_BASE = "https://api.perchfitness.com"  # ⚠ confirm base URL from Swagger docs

# /v2/users response field names:
_USER_ID_FIELD         = "id"          # ⚠ confirm
_USER_FIRST_NAME_FIELD = "first_name"  # ⚠ confirm
_USER_LAST_NAME_FIELD  = "last_name"   # ⚠ confirm
_USERS_LIST_KEY        = "users"       # ⚠ key inside response JSON that holds the list

# /stats response field names:
_STAT_USER_ID_FIELD  = "user_id"  # ⚠ confirm
_STAT_EXERCISE_FIELD = "exercise" # ⚠ confirm
_STAT_ONE_RM_FIELD   = "ONE_RM"   # from design doc — confirm capitalization
_STAT_DATE_FIELD     = "date"     # ⚠ confirm
_STATS_LIST_KEY      = "stats"    # ⚠ key inside response JSON that holds the list
_NEXT_TOKEN_KEY      = "next_token"  # pagination field

# Perch exercise name → internal short key.
# ⚠ Verify strings match exactly what the API returns in _STAT_EXERCISE_FIELD.
_EXERCISE_MAP = {
    "Back Squat":       "bs",
    "Power Clean":      "pc",
    "Bench Press":      "bp",
    "Hang Power Clean": "hpc",
}
# ────────────────────────────────────────────────────────────────────────────


def _normalize_name(name: str) -> str:
    """Lowercase, strip extra whitespace, remove punctuation."""
    return re.sub(r"[^a-z ]", "", name.strip().lower())


# ── DB helpers ───────────────────────────────────────────────────────────────

def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create perch_1rm table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS perch_1rm (
            name_normalized TEXT NOT NULL,
            perch_user_id   TEXT NOT NULL,
            exercise        TEXT NOT NULL,
            one_rm_lbs      REAL NOT NULL,
            test_date       DATE NOT NULL,
            PRIMARY KEY (name_normalized, exercise, test_date)
        )
    """)


def upsert_rows(conn: duckdb.DuckDBPyConnection, rows: list[dict]) -> None:
    """Insert rows, replacing on (name_normalized, exercise, test_date) conflict."""
    if not rows:
        return
    for row in rows:
        conn.execute("""
            DELETE FROM perch_1rm
            WHERE name_normalized = ? AND exercise = ? AND test_date = ?
        """, [row["name_normalized"], row["exercise"], row["test_date"]])
    conn.executemany("""
        INSERT INTO perch_1rm (name_normalized, perch_user_id, exercise, one_rm_lbs, test_date)
        VALUES (?, ?, ?, ?, ?)
    """, [
        [r["name_normalized"], r["perch_user_id"], r["exercise"], r["one_rm_lbs"], r["test_date"]]
        for r in rows
    ])
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_perch.py::test_ensure_schema_creates_table tests/test_perch.py::test_upsert_rows_inserts_and_deduplicates -v
```
Expected: both PASS

- [ ] **Step 5: Commit**

```bash
git add src/perch_ingest.py tests/test_perch.py
git commit -m "feat: Perch ingest — DB schema and upsert (no HTTP)"
```

---

## Task 3: Perch ingest — HTTP client and CLI

**Files:**
- Modify: `src/perch_ingest.py` (add HTTP functions + `ingest()` + `main()`)

> No automated test for the HTTP layer — it requires a live token. The `--probe` flag lets Eric inspect raw responses and verify `_API` constants before full ingest.

- [ ] **Step 1: Append HTTP client to src/perch_ingest.py**

Add these functions after `upsert_rows`:

```python
# ── HTTP client ──────────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def fetch_users(token: str) -> dict[str, str]:
    """
    GET /v2/users (paginated).
    Returns {perch_user_id: name_normalized} for all users in account.
    """
    url = f"{PERCH_API_BASE}/v2/users"
    id_to_name: dict[str, str] = {}
    params: dict = {}

    while True:
        resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        users = body.get("data", body).get(_USERS_LIST_KEY, [])
        for u in users:
            uid   = u.get(_USER_ID_FIELD)
            first = u.get(_USER_FIRST_NAME_FIELD, "")
            last  = u.get(_USER_LAST_NAME_FIELD, "")
            if uid:
                id_to_name[uid] = _normalize_name(f"{first} {last}")

        next_tok = body.get("data", body).get(_NEXT_TOKEN_KEY)
        if not next_tok:
            break
        params = {_NEXT_TOKEN_KEY: next_tok}

    return id_to_name


def fetch_stats(token: str, start_date: str, end_date: str) -> list[dict]:
    """
    GET /stats (paginated, date-filtered).
    Returns raw stat records from API.
    """
    url = f"{PERCH_API_BASE}/stats"
    all_stats: list[dict] = []
    params: dict = {"start_date": start_date, "end_date": end_date}

    while True:
        resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        stats = body.get("data", body).get(_STATS_LIST_KEY, [])
        all_stats.extend(stats)

        next_tok = body.get("data", body).get(_NEXT_TOKEN_KEY)
        if not next_tok:
            break
        params = {_NEXT_TOKEN_KEY: next_tok, "start_date": start_date, "end_date": end_date}

    return all_stats


def ingest(start_date: str, end_date: str, token: str, db_path=None) -> int:
    """
    Full ingest: fetch users + stats → upsert into perch.duckdb.
    Returns number of rows written.
    """
    if db_path is None:
        db_path = PERCH_DB

    print("Fetching Perch users ...")
    id_to_name = fetch_users(token)
    print(f"  {len(id_to_name)} athletes found")

    print(f"Fetching Perch stats ({start_date} to {end_date}) ...")
    raw_stats = fetch_stats(token, start_date, end_date)
    print(f"  {len(raw_stats)} raw stat records")

    rows = []
    skipped_exercise = set()
    for stat in raw_stats:
        uid      = stat.get(_STAT_USER_ID_FIELD)
        exercise = stat.get(_STAT_EXERCISE_FIELD)
        one_rm   = stat.get(_STAT_ONE_RM_FIELD)
        date     = stat.get(_STAT_DATE_FIELD)

        if not uid or not exercise or one_rm is None or not date:
            continue
        if exercise not in _EXERCISE_MAP:
            skipped_exercise.add(exercise)
            continue

        name_norm = id_to_name.get(uid)
        if not name_norm:
            continue

        rows.append({
            "name_normalized": name_norm,
            "perch_user_id":   uid,
            "exercise":        exercise,
            "one_rm_lbs":      float(one_rm),
            "test_date":       str(date)[:10],
        })

    if skipped_exercise:
        print(f"  Skipped exercises (not in _EXERCISE_MAP): {sorted(skipped_exercise)}")

    conn = duckdb.connect(str(db_path))
    ensure_schema(conn)
    upsert_rows(conn, rows)
    conn.close()

    print(f"  Upserted {len(rows)} rows to {db_path}")
    return len(rows)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest Perch 1RM data into local DuckDB cache")
    parser.add_argument("--start",  required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",    required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--probe",  action="store_true",
                        help="Dump raw /v2/users and /stats responses to verify field names, then exit")
    args = parser.parse_args()

    token = os.environ.get("PERCH_API_TOKEN")
    if not token:
        sys.exit("ERROR: PERCH_API_TOKEN not set. Add it to .env or export it.")

    if args.probe:
        print("=== /v2/users (first page) ===")
        import json
        resp = requests.get(f"{PERCH_API_BASE}/v2/users", headers=_headers(token), timeout=30)
        print(json.dumps(resp.json(), indent=2)[:3000])
        print("\n=== /stats (first page) ===")
        resp2 = requests.get(f"{PERCH_API_BASE}/stats", headers=_headers(token),
                             params={"start_date": args.start, "end_date": args.end}, timeout=30)
        print(json.dumps(resp2.json(), indent=2)[:3000])
        print("\n⚠  Verify field names match constants in src/perch_ingest.py before full ingest.")
        return

    ingest(args.start, args.end, token)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual verification (first-time only)**

Before running full ingest, probe the API to confirm field names:

```bash
# Copy .env.example to .env and fill in the token
cp .env.example .env
# Edit .env: PERCH_API_TOKEN=<real token>

python src/perch_ingest.py --start 2025-09-01 --end 2026-03-28 --probe
```

Check the output and verify:
- `_USER_ID_FIELD`, `_USER_FIRST_NAME_FIELD`, `_USER_LAST_NAME_FIELD` match `/v2/users` user objects
- `_STAT_USER_ID_FIELD`, `_STAT_EXERCISE_FIELD`, `_STAT_ONE_RM_FIELD`, `_STAT_DATE_FIELD` match `/stats` stat objects
- `_EXERCISE_MAP` keys match exact exercise name strings returned by the API

If any constants are wrong, update them in `perch_ingest.py` before proceeding.

- [ ] **Step 3: Run full ingest**

```bash
python src/perch_ingest.py --start 2025-09-01 --end 2026-03-28
```

Expected output:
```
Fetching Perch users ...
  N athletes found
Fetching Perch stats (2025-09-01 to 2026-03-28) ...
  M raw stat records
  Upserted K rows to data/perch.duckdb
```

Verify the cache:

```bash
python -c "
import duckdb
conn = duckdb.connect('data/perch.duckdb', read_only=True)
print(conn.execute('SELECT exercise, COUNT(*) FROM perch_1rm GROUP BY exercise').df())
print(conn.execute('SELECT COUNT(DISTINCT name_normalized) FROM perch_1rm').fetchone())
"
```

- [ ] **Step 4: Commit**

```bash
git add src/perch_ingest.py
git commit -m "feat: Perch ingest — HTTP client, pagination, CLI with --probe"
```

---

## Task 4: data.py — load_perch() and load_perch_history()

**Files:**
- Modify: `src/data.py`
- Modify: `tests/test_perch.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_perch.py`:

```python
def _make_perch_db(tmp_path: str, rows: list[dict]) -> None:
    """Helper: create a temp perch.duckdb with given rows."""
    conn = duckdb.connect(tmp_path)
    from src.perch_ingest import ensure_schema, upsert_rows
    ensure_schema(conn)
    upsert_rows(conn, rows)
    conn.close()


def _make_roster_csv(tmp_path: str) -> None:
    import csv
    with open(tmp_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["full_name", "jersey_number", "position", "catapult_id", "forcedecks_id"])
        writer.writeheader()
        writer.writerow({"full_name": "Alice Smith", "jersey_number": "", "position": "WR",
                         "catapult_id": "c1", "forcedecks_id": "fd1"})
        writer.writerow({"full_name": "Bob Jones",   "jersey_number": "", "position": "OL",
                         "catapult_id": "c2", "forcedecks_id": "fd2"})


def _make_bw_csv(tmp_path: str) -> None:
    with open(tmp_path, "w") as f:
        f.write("DATE,NAME,WEIGHT,POS\n")
        f.write('10/01/2025,"Smith, Alice",150,WR\n')   # 150 lbs
        f.write('10/01/2025,"Jones, Bob",220,OL\n')      # 220 lbs


def test_load_perch_returns_normalized_ratios(tmp_path):
    """1RM / BW ratios computed correctly from cache."""
    import tempfile
    from unittest.mock import patch

    db_tmp   = str(tmp_path / "perch.duckdb")
    roster_tmp = str(tmp_path / "roster.csv")
    bw_tmp   = str(tmp_path / "bw.csv")

    _make_roster_csv(roster_tmp)
    _make_bw_csv(bw_tmp)
    _make_perch_db(db_tmp, [
        # Alice: BS 300 lbs / 150 lbs BW = 2.0
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 300.0, "test_date": "2025-10-15"},
        # Bob: no Perch data
    ])

    from src.data import load_perch
    with patch("src.data.PERCH_DB", db_tmp), \
         patch("src.data.ROSTER_CSV", roster_tmp), \
         patch("src.data.BODYWEIGHT_CSV", bw_tmp):
        df = load_perch("2025-09-01", "2026-03-28")

    assert "bs_1rm_bw" in df.columns
    alice = df[df["forcedecks_id"] == "fd1"]
    assert len(alice) == 1
    assert alice["bs_1rm_bw"].iloc[0] == pytest.approx(2.0, rel=1e-4)

    bob = df[df["forcedecks_id"] == "fd2"]
    assert len(bob) == 0 or bob["bs_1rm_bw"].isna().all()


def test_load_perch_history_multiple_dates(tmp_path):
    """History loader returns one row per date (not just most recent)."""
    import tempfile
    from unittest.mock import patch

    db_tmp     = str(tmp_path / "perch.duckdb")
    roster_tmp = str(tmp_path / "roster.csv")
    bw_tmp     = str(tmp_path / "bw.csv")

    _make_roster_csv(roster_tmp)
    _make_bw_csv(bw_tmp)
    _make_perch_db(db_tmp, [
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 280.0, "test_date": "2025-09-01"},
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 300.0, "test_date": "2025-10-15"},
    ])

    from src.data import load_perch_history
    with patch("src.data.PERCH_DB", db_tmp), \
         patch("src.data.ROSTER_CSV", roster_tmp), \
         patch("src.data.BODYWEIGHT_CSV", bw_tmp):
        df = load_perch_history("2025-09-01", "2026-03-28")

    alice_rows = df[df["forcedecks_id"] == "fd1"]
    assert len(alice_rows) == 2, f"Expected 2 history rows, got {len(alice_rows)}"
    assert list(alice_rows["test_date"].astype(str).str[:10]) == ["2025-09-01", "2025-10-15"]


def test_load_perch_missing_db_returns_empty():
    """If perch.duckdb doesn't exist, load_perch() returns empty DataFrame."""
    from unittest.mock import patch
    from src.data import load_perch

    with patch("src.data.PERCH_DB", "/nonexistent/path/perch.duckdb"):
        df = load_perch("2025-09-01", "2026-03-28")

    assert df.empty or df["bs_1rm_bw"].isna().all()
    assert "forcedecks_id" in df.columns
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_perch.py::test_load_perch_returns_normalized_ratios tests/test_perch.py::test_load_perch_history_multiple_dates tests/test_perch.py::test_load_perch_missing_db_returns_empty -v
```
Expected: `ImportError: cannot import name 'load_perch' from 'src.data'`

- [ ] **Step 3: Add imports and constants to data.py**

At the top of `src/data.py`, add `PERCH_DB` to the config import:

```python
from config import FORCEPLATE_DB, GPS_DB, BODYWEIGHT_CSV, ROSTER_CSV, PERCH_DB
```

- [ ] **Step 4: Add load_perch() to data.py**

Append after `load_imtp_history()`:

```python
def _load_bw_lbs(end_date: str) -> pd.DataFrame:
    """
    Internal helper: most recent body weight per athlete on or before end_date, in lbs.
    Returns: name_normalized, weight_lbs
    """
    df = load_bodyweight(end_date)          # returns weight_kg
    df["weight_lbs"] = df["weight_kg"] / 0.453592
    return df[["name_normalized", "weight_lbs"]]


def load_perch(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Most recent 1RM per exercise per athlete within [start_date, end_date],
    normalized by snapshot body weight (end_date).
    Returns: forcedecks_id, bs_1rm_bw, pc_1rm_bw, bp_1rm_bw, hpc_1rm_bw
    Athletes with no Perch data are not included (merge_all left-joins on forcedecks_id).
    Returns empty DataFrame if perch.duckdb doesn't exist or has no data.
    """
    empty = pd.DataFrame(columns=["forcedecks_id", "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"])

    if not PERCH_DB.exists():
        return empty

    try:
        conn = duckdb.connect(str(PERCH_DB), read_only=True)
        tables = conn.execute("SHOW TABLES").df()
        if "perch_1rm" not in tables["name"].tolist():
            conn.close()
            return empty

        # Most recent 1RM per athlete per exercise in period
        latest = conn.execute("""
            SELECT name_normalized, exercise, one_rm_lbs
            FROM (
                SELECT name_normalized, exercise, one_rm_lbs,
                       ROW_NUMBER() OVER (
                           PARTITION BY name_normalized, exercise
                           ORDER BY test_date DESC
                       ) AS rn
                FROM perch_1rm
                WHERE test_date BETWEEN ? AND ?
            ) t
            WHERE rn = 1
        """, [start_date, end_date]).df()
        conn.close()
    except Exception:
        return empty

    if latest.empty:
        return empty

    # Pivot exercises wide: one column per exercise
    pivoted = latest.pivot_table(
        index="name_normalized", columns="exercise", values="one_rm_lbs"
    ).reset_index()
    pivoted.columns.name = None

    # Ensure all 4 exercise columns exist (fill missing with NaN)
    for ex, short in [("Back Squat", "bs"), ("Power Clean", "pc"),
                      ("Bench Press", "bp"), ("Hang Power Clean", "hpc")]:
        col = f"{short}_1rm_lbs"
        pivoted[col] = pivoted[ex] if ex in pivoted.columns else float("nan")

    pivoted = pivoted[["name_normalized", "bs_1rm_lbs", "pc_1rm_lbs", "bp_1rm_lbs", "hpc_1rm_lbs"]]

    # Join roster to get forcedecks_id
    roster = pd.read_csv(ROSTER_CSV)
    roster["name_normalized"] = roster["full_name"].apply(_normalize_name)
    pivoted = pivoted.merge(roster[["name_normalized", "forcedecks_id"]], on="name_normalized", how="inner")

    # Normalize by snapshot body weight
    bw = _load_bw_lbs(end_date)
    pivoted = pivoted.merge(bw, on="name_normalized", how="left")

    for ex in ["bs", "pc", "bp", "hpc"]:
        raw_col = f"{ex}_1rm_lbs"
        ratio_col = f"{ex}_1rm_bw"
        pivoted[ratio_col] = pivoted[raw_col] / pivoted["weight_lbs"]

    cols = ["forcedecks_id", "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"]
    return pivoted[cols].reset_index(drop=True)


def load_perch_history(start_date: str, end_date: str) -> pd.DataFrame:
    """
    All Perch 1RM records per athlete within [start_date, end_date],
    pivoted wide per test_date, normalized by snapshot body weight (end_date).
    Returns: forcedecks_id, test_date, bs_1rm_bw, pc_1rm_bw, bp_1rm_bw, hpc_1rm_bw
    Sorted by forcedecks_id, test_date ASC.
    """
    empty = pd.DataFrame(columns=["forcedecks_id", "test_date",
                                   "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"])

    if not PERCH_DB.exists():
        return empty

    try:
        conn = duckdb.connect(str(PERCH_DB), read_only=True)
        tables = conn.execute("SHOW TABLES").df()
        if "perch_1rm" not in tables["name"].tolist():
            conn.close()
            return empty

        all_rows = conn.execute("""
            SELECT name_normalized, exercise, one_rm_lbs, test_date
            FROM perch_1rm
            WHERE test_date BETWEEN ? AND ?
            ORDER BY name_normalized, test_date
        """, [start_date, end_date]).df()
        conn.close()
    except Exception:
        return empty

    if all_rows.empty:
        return empty

    # Pivot: one column per exercise, one row per (athlete, date)
    pivoted = all_rows.pivot_table(
        index=["name_normalized", "test_date"], columns="exercise", values="one_rm_lbs"
    ).reset_index()
    pivoted.columns.name = None

    for ex, short in [("Back Squat", "bs"), ("Power Clean", "pc"),
                      ("Bench Press", "bp"), ("Hang Power Clean", "hpc")]:
        col = f"{short}_1rm_lbs"
        pivoted[col] = pivoted[ex] if ex in pivoted.columns else float("nan")

    # Join roster
    roster = pd.read_csv(ROSTER_CSV)
    roster["name_normalized"] = roster["full_name"].apply(_normalize_name)
    pivoted = pivoted.merge(roster[["name_normalized", "forcedecks_id"]], on="name_normalized", how="inner")

    # Normalize by snapshot BW
    bw = _load_bw_lbs(end_date)
    pivoted = pivoted.merge(bw, on="name_normalized", how="left")

    for ex in ["bs", "pc", "bp", "hpc"]:
        pivoted[f"{ex}_1rm_bw"] = pivoted[f"{ex}_1rm_lbs"] / pivoted["weight_lbs"]

    cols = ["forcedecks_id", "test_date", "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"]
    for c in cols:
        if c not in pivoted.columns:
            pivoted[c] = float("nan")

    return pivoted[cols].sort_values(["forcedecks_id", "test_date"]).reset_index(drop=True)
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_perch.py::test_load_perch_returns_normalized_ratios tests/test_perch.py::test_load_perch_history_multiple_dates tests/test_perch.py::test_load_perch_missing_db_returns_empty -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/data.py tests/test_perch.py
git commit -m "feat: data.py — load_perch() and load_perch_history() with BW normalization"
```

---

## Task 5: data.py — update merge_all()

**Files:**
- Modify: `src/data.py`
- Modify: `tests/test_perch.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_perch.py`:

```python
def test_merge_all_includes_perch_columns(tmp_path):
    """merge_all() result has bs_1rm_bw column (NaN if no Perch data)."""
    from unittest.mock import patch

    db_tmp     = str(tmp_path / "perch.duckdb")
    roster_tmp = str(tmp_path / "roster.csv")
    bw_tmp     = str(tmp_path / "bw.csv")

    _make_roster_csv(roster_tmp)
    _make_bw_csv(bw_tmp)

    # No Perch DB — should still work gracefully
    from src.data import merge_all
    import duckdb

    # Stub out the real DBs so test doesn't need them
    empty_fp = pd.DataFrame(columns=["forcedecks_id", "jump_height_cm", "peak_power_bm", "mrsi"])
    empty_gps = pd.DataFrame(columns=["catapult_id", "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms"])
    empty_imtp = pd.DataFrame(columns=["forcedecks_id", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    with patch("src.data.PERCH_DB", "/nonexistent/perch.duckdb"), \
         patch("src.data.ROSTER_CSV", roster_tmp), \
         patch("src.data.BODYWEIGHT_CSV", bw_tmp), \
         patch("src.data.load_cmj", return_value=empty_fp), \
         patch("src.data.load_gps", return_value=empty_gps), \
         patch("src.data.load_imtp", return_value=empty_imtp):
        df = merge_all("2025-09-01", "2026-03-28")

    assert "bs_1rm_bw" in df.columns, "merge_all() must include bs_1rm_bw"
    assert df["bs_1rm_bw"].isna().all(), "No Perch DB → all NaN"
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_perch.py::test_merge_all_includes_perch_columns -v
```
Expected: `AssertionError: merge_all() must include bs_1rm_bw`

- [ ] **Step 3: Update merge_all() in data.py**

Replace the `merge_all` function body:

```python
def merge_all(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Joins CMJ, GPS, body weight, IMTP, and Perch 1RM onto the athlete roster crosswalk.
    Athletes missing any domain get NaN for that domain's metrics.
    """
    roster = pd.read_csv(ROSTER_CSV)
    roster["name_normalized"] = roster["full_name"].apply(_normalize_name)

    cmj   = load_cmj(start_date, end_date)
    gps   = load_gps(start_date, end_date)
    bw    = load_bodyweight(end_date)
    imtp  = load_imtp(start_date, end_date)
    perch = load_perch(start_date, end_date)

    df = roster.merge(cmj,   on="forcedecks_id",  how="left")
    df = df.merge(gps,   on="catapult_id",    how="left")
    df = df.merge(bw,    on="name_normalized", how="left")
    df = df.merge(imtp,  on="forcedecks_id",  how="left")
    df = df.merge(perch, on="forcedecks_id",  how="left")

    return df
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_perch.py::test_merge_all_includes_perch_columns -v
```
Expected: PASS

- [ ] **Step 5: Run full test suite to check no regressions**

```
pytest tests/ -v
```
Expected: all existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/data.py tests/test_perch.py
git commit -m "feat: data.py — merge_all() includes Perch 1RM domain"
```

---

## Task 6: scorer.py — Weight Room domain

**Files:**
- Modify: `src/scorer.py`
- Modify: `tests/test_history.py`

- [ ] **Step 1: Write failing tests**

Open `tests/test_history.py`. Update `_make_df()` to include Perch columns and update `pop_stats` test:

```python
def _make_df():
    """Minimal 3-athlete DataFrame with all required columns including Perch."""
    return pd.DataFrame({
        "forcedecks_id":      ["a", "b", "c"],
        "catapult_id":        ["c1", "c2", None],
        "full_name":          ["Alice Smith", "Bob Jones", "Carol Lee"],
        "position":           ["WR", "OL", "QB"],
        "jersey_number":      [None, None, None],
        "name_normalized":    ["alice smith", "bob jones", "carol lee"],
        "jump_height_cm":     [60.0, 70.0, 65.0],
        "peak_power_bm":      [20.0, 25.0, 22.5],
        "mrsi":               [2.0, 3.0, 2.5],
        "avg_hsd_m":          [400.0, 500.0, None],
        "avg_player_load":    [100.0, 120.0, None],
        "avg_max_velocity_ms":[7.5, 8.5, None],
        "weight_kg":          [80.0, 110.0, 90.0],
        "peak_force_bm":      [25.0, 35.0, 30.0],
        "peak_force_n":       [2000.0, 3850.0, 2700.0],
        "rfd_100ms":          [6000.0, 9000.0, 7500.0],
        "rfd_200ms":          [5000.0, 8000.0, 6500.0],
        # Perch — Carol has no Weight Room data
        "bs_1rm_bw":          [2.0, 2.5, None],
        "pc_1rm_bw":          [1.3, 1.6, None],
        "bp_1rm_bw":          [1.1, 1.4, None],
        "hpc_1rm_bw":         [1.2, 1.5, None],
    })
```

Append new tests after the existing ones in `tests/test_history.py`:

```python
def test_scorer_has_weight_room_domain():
    df = _make_df()
    df_scored, _ = score(df)
    assert "weight_room_domain" in df_scored.columns, "scorer must produce weight_room_domain"


def test_weight_room_nan_for_missing_perch():
    """Athlete with no Perch data gets NaN weight_room_domain (not 50)."""
    df = _make_df()
    df_scored, _ = score(df)
    carol = df_scored[df_scored["full_name"] == "Carol Lee"]
    assert carol["weight_room_domain"].isna().all(), \
        "Carol has no Perch 1RMs — weight_room_domain must be NaN"


def test_tsa_still_scores_without_weight_room():
    """Athletes missing Weight Room domain still get a TSA from 4 domains."""
    df = _make_df()
    df_scored, _ = score(df)
    carol = df_scored[df_scored["full_name"] == "Carol Lee"]
    assert carol["tsa_score"].notna().all(), "TSA must not be NaN when Weight Room is missing"


def test_missing_domains_includes_weight_room_label():
    df = _make_df()
    df_scored, _ = score(df)
    carol = df_scored[df_scored["full_name"] == "Carol Lee"]
    assert "Weight Room" in carol["missing_domains"].iloc[0]


def test_pop_stats_has_perch_keys():
    df = _make_df()
    _, pop_stats = score(df)
    for key in ["bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"]:
        assert key in pop_stats, f"pop_stats missing Perch key: {key}"


def test_scored_df_has_five_domain_columns():
    df = _make_df()
    df_scored, _ = score(df)
    for col in ["cmj_domain", "gps_domain", "bw_domain", "strength_domain", "weight_room_domain"]:
        assert col in df_scored.columns, f"Missing domain column: {col}"
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_history.py::test_scorer_has_weight_room_domain tests/test_history.py::test_weight_room_nan_for_missing_perch tests/test_history.py::test_tsa_still_scores_without_weight_room tests/test_history.py::test_missing_domains_includes_weight_room_label tests/test_history.py::test_pop_stats_has_perch_keys tests/test_history.py::test_scored_df_has_five_domain_columns -v
```
Expected: `AssertionError` on `weight_room_domain` missing

- [ ] **Step 3: Update scorer.py**

Replace the entire `src/scorer.py` with:

```python
"""TSA scoring: z-scores → t-scores → domain composites → TSA composite → RAG."""

import numpy as np
import pandas as pd


_METRICS = {
    "jump_height_cm":      "jump_height_t",
    "peak_power_bm":       "peak_power_bm_t",
    "mrsi":                "mrsi_t",
    "avg_hsd_m":           "hsd_t",
    "avg_player_load":     "player_load_t",
    "avg_max_velocity_ms": "max_vel_t",
    "weight_kg":           "weight_t",
    "peak_force_bm":       "peak_force_bm_t",
    "peak_force_n":        "peak_force_n_t",
    "rfd_100ms":           "rfd_100ms_t",
    "rfd_200ms":           "rfd_200ms_t",
    # Weight Room (Perch 1RM / BW, dimensionless ratios)
    "bs_1rm_bw":           "bs_1rm_bw_t",
    "pc_1rm_bw":           "pc_1rm_bw_t",
    "bp_1rm_bw":           "bp_1rm_bw_t",
    "hpc_1rm_bw":          "hpc_1rm_bw_t",
}

_CMJ_T          = ["jump_height_t", "peak_power_bm_t", "mrsi_t"]
_GPS_T          = ["hsd_t", "player_load_t", "max_vel_t"]
_BW_T           = ["weight_t"]
_STRENGTH_T     = ["peak_force_bm_t"]
_WEIGHT_ROOM_T  = ["bs_1rm_bw_t", "pc_1rm_bw_t", "bp_1rm_bw_t", "hpc_1rm_bw_t"]


def _z_to_t(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.std() == 0 or len(valid) < 2:
        return pd.Series(50.0, index=series.index)
    z = (series - valid.mean()) / valid.std()
    return (z * 10 + 50).clip(0, 100)


def score(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Adds t-score columns, domain scores, TSA composite, TSA rank, and RAG to df.
    Operates on available data only — athletes missing a domain get NaN for that domain.
    Returns (scored_df sorted by tsa_rank, pop_stats dict with mean/std per raw metric).
    """
    out = df.copy()
    pop_stats = {}

    for raw_col, t_col in _METRICS.items():
        series = out[raw_col] if raw_col in out.columns else pd.Series(dtype=float, index=out.index)
        valid = series.dropna()
        if len(valid) >= 2 and valid.std() > 0:
            pop_stats[raw_col] = {"mean": float(valid.mean()), "std": float(valid.std())}
        else:
            pop_stats[raw_col] = {"mean": None, "std": None}
        out[t_col] = _z_to_t(series) if raw_col in out.columns else pd.Series(50.0, index=out.index)

    out["cmj_domain"]         = out[_CMJ_T].mean(axis=1, skipna=False)
    out["gps_domain"]         = out[_GPS_T].mean(axis=1, skipna=False)
    out["bw_domain"]          = out[_BW_T].mean(axis=1, skipna=False)
    out["strength_domain"]    = out[_STRENGTH_T].mean(axis=1, skipna=False)
    # Weight Room: partial data still scores (athlete may not have all 4 exercises)
    out["weight_room_domain"] = out[_WEIGHT_ROOM_T].mean(axis=1, skipna=True)
    # skipna=True: NaN if all exercises missing; partial mean if some exercises present
    out["weight_room_domain"] = out["weight_room_domain"].where(
        out[_WEIGHT_ROOM_T].notna().any(axis=1), other=float("nan")
    )

    domain_cols = ["cmj_domain", "gps_domain", "bw_domain", "strength_domain", "weight_room_domain"]
    out["tsa_score"] = out[domain_cols].mean(axis=1, skipna=True)

    out["tsa_rank"] = out["tsa_score"].rank(ascending=False, method="min").astype("Int64")

    green_thresh = out["tsa_score"].quantile(2 / 3)
    amber_thresh = out["tsa_score"].quantile(1 / 3)
    out["rag"] = np.select(
        [out["tsa_score"] >= green_thresh, out["tsa_score"] >= amber_thresh],
        ["green", "amber"],
        default="red",
    )

    missing = []
    for _, row in out.iterrows():
        domains = []
        if pd.isna(row["cmj_domain"]):          domains.append("CMJ")
        if pd.isna(row["gps_domain"]):          domains.append("GPS")
        if pd.isna(row["bw_domain"]):           domains.append("BW")
        if pd.isna(row["strength_domain"]):     domains.append("Strength")
        if pd.isna(row["weight_room_domain"]):  domains.append("Weight Room")
        missing.append(", ".join(domains))
    out["missing_domains"] = missing

    return out.sort_values("tsa_rank").reset_index(drop=True), pop_stats
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/ -v
```
Expected: all tests PASS (including existing ones)

- [ ] **Step 5: Commit**

```bash
git add src/scorer.py tests/test_history.py
git commit -m "feat: scorer.py — Weight Room domain (5th TSA domain, Perch 1RM/BW)"
```

---

## Task 7: renderer.py — Perch integration

**Files:**
- Modify: `src/renderer.py`
- Modify: `tests/test_history.py`

- [ ] **Step 1: Update existing build_history tests to use new 7-arg signature**

The existing `test_build_history_attaches_empty_lists_when_no_data` and `test_build_history_cmj_t_scores` tests call `build_history()` with 6 args. After this task's implementation, the signature requires 7. Update both calls in `tests/test_history.py`:

In `test_build_history_attaches_empty_lists_when_no_data`, replace:
```python
build_history(athletes, empty_df_cmj, empty_df_gps, empty_df_bw, empty_df_imtp, pop_stats)
```
with:
```python
empty_perch = pd.DataFrame(columns=["forcedecks_id", "test_date",
                                     "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"])
build_history(athletes, empty_df_cmj, empty_df_gps, empty_df_bw, empty_df_imtp, empty_perch, pop_stats)
```
And add this assertion at the end:
```python
assert athletes[0]["perch_history"] == []
```

In `test_build_history_cmj_t_scores`, find:
```python
    build_history(
        athletes, cmj_hist,
        empty(["catapult_id","session_date","hsd_m","player_load","max_velocity_ms"]),
        empty(["name_normalized","date","weight_kg"]),
        empty(["forcedecks_id","test_date","peak_force_n","peak_force_bm","rfd_100ms","rfd_200ms"]),
        pop_stats,
    )
```
Replace with:
```python
    build_history(
        athletes, cmj_hist,
        empty(["catapult_id","session_date","hsd_m","player_load","max_velocity_ms"]),
        empty(["name_normalized","date","weight_kg"]),
        empty(["forcedecks_id","test_date","peak_force_n","peak_force_bm","rfd_100ms","rfd_200ms"]),
        empty(["forcedecks_id","test_date","bs_1rm_bw","pc_1rm_bw","bp_1rm_bw","hpc_1rm_bw"]),
        pop_stats,
    )
```

- [ ] **Step 2: Write new failing tests**

Append to `tests/test_history.py`:

```python
def _make_pop_stats_with_perch():
    return {
        "jump_height_cm":     {"mean": 65.0, "std": 5.0},
        "peak_power_bm":      {"mean": 22.0, "std": 2.0},
        "mrsi":               {"mean": 2.5,  "std": 0.3},
        "avg_hsd_m":          {"mean": 450.0, "std": 50.0},
        "avg_player_load":    {"mean": 110.0, "std": 15.0},
        "avg_max_velocity_ms":{"mean": 8.0,   "std": 0.5},
        "weight_kg":          {"mean": 90.0,  "std": 10.0},
        "peak_force_bm":      {"mean": 30.0,  "std": 3.0},
        "peak_force_n":       {"mean": 2700.0,"std": 400.0},
        "rfd_100ms":          {"mean": 7500.0,"std": 1000.0},
        "rfd_200ms":          {"mean": 6000.0,"std": 800.0},
        "bs_1rm_bw":          {"mean": 2.0,  "std": 0.3},
        "pc_1rm_bw":          {"mean": 1.4,  "std": 0.2},
        "bp_1rm_bw":          {"mean": 1.2,  "std": 0.2},
        "hpc_1rm_bw":         {"mean": 1.3,  "std": 0.2},
    }


def test_build_history_attaches_perch_history():
    from src.renderer import build_history

    athletes = [{"forcedecks_id": "fd1", "catapult_id": None, "full_name": "Alice Smith"}]
    pop_stats = _make_pop_stats_with_perch()

    perch_hist = pd.DataFrame([{
        "forcedecks_id": "fd1",
        "test_date":     "2025-10-15",
        "bs_1rm_bw":     2.3,
        "pc_1rm_bw":     1.6,
        "bp_1rm_bw":     None,
        "hpc_1rm_bw":    None,
    }])

    empty = lambda cols: pd.DataFrame(columns=cols)
    build_history(
        athletes,
        empty(["forcedecks_id","test_date","jump_height_cm","peak_power_bm","mrsi"]),
        empty(["catapult_id","session_date","hsd_m","player_load","max_velocity_ms"]),
        empty(["name_normalized","date","weight_kg"]),
        empty(["forcedecks_id","test_date","peak_force_n","peak_force_bm","rfd_100ms","rfd_200ms"]),
        perch_hist,
        pop_stats,
    )

    h = athletes[0]["perch_history"]
    assert len(h) == 1, f"Expected 1 perch_history entry, got {len(h)}"
    assert h[0]["date"] == "2025-10-15"
    assert h[0]["bs_1rm_bw"] == pytest.approx(2.3)
    assert h[0]["bs_1rm_bw_t"] == pytest.approx(60.0, abs=1.0)  # z = (2.3-2.0)/0.3 = 1 → t=60
    assert h[0]["bp_1rm_bw"] is None


def test_build_history_empty_perch_attaches_empty_list():
    from src.renderer import build_history

    athletes = [{"forcedecks_id": "fd1", "catapult_id": None, "full_name": "Alice Smith"}]
    pop_stats = _make_pop_stats_with_perch()
    empty = lambda cols: pd.DataFrame(columns=cols)

    build_history(
        athletes,
        empty(["forcedecks_id","test_date","jump_height_cm","peak_power_bm","mrsi"]),
        empty(["catapult_id","session_date","hsd_m","player_load","max_velocity_ms"]),
        empty(["name_normalized","date","weight_kg"]),
        empty(["forcedecks_id","test_date","peak_force_n","peak_force_bm","rfd_100ms","rfd_200ms"]),
        empty(["forcedecks_id","test_date","bs_1rm_bw","pc_1rm_bw","bp_1rm_bw","hpc_1rm_bw"]),
        pop_stats,
    )

    assert athletes[0]["perch_history"] == []
```

- [ ] **Step 3: Run to verify they fail**

```
pytest tests/test_history.py::test_build_history_attaches_perch_history tests/test_history.py::test_build_history_empty_perch_attaches_empty_list -v
```
Expected: `TypeError: build_history() takes 6 positional arguments but 7 were given` (or similar)

- [ ] **Step 4: Update renderer.py — _Z_MAP**

In `src/renderer.py`, add 4 entries to `_Z_MAP`:

```python
_Z_MAP = {
    "jump_height_cm":      "jump_height_z",
    "peak_power_bm":       "peak_power_bm_z",
    "mrsi":                "mrsi_z",
    "avg_hsd_m":           "hsd_z",
    "avg_player_load":     "player_load_z",
    "avg_max_velocity_ms": "max_vel_z",
    "weight_kg":           "weight_z",
    "peak_force_bm":       "peak_force_bm_z",
    "peak_force_n":        "peak_force_n_z",
    "rfd_100ms":           "rfd_100ms_z",
    "rfd_200ms":           "rfd_200ms_z",
    # Weight Room
    "bs_1rm_bw":           "bs_1rm_bw_z",
    "pc_1rm_bw":           "pc_1rm_bw_z",
    "bp_1rm_bw":           "bp_1rm_bw_z",
    "hpc_1rm_bw":          "hpc_1rm_bw_z",
}
```

- [ ] **Step 5: Update renderer.py — include_cols**

In the `render()` function, update `include_cols`:

```python
include_cols = [
    "full_name", "jersey_number", "position", "catapult_id", "forcedecks_id",
    "jump_height_cm", "peak_power_bm", "mrsi",
    "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms", "weight_kg",
    "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms",
    "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw",
    "jump_height_t", "peak_power_bm_t", "mrsi_t",
    "hsd_t", "player_load_t", "max_vel_t", "weight_t",
    "peak_force_bm_t", "peak_force_n_t", "rfd_100ms_t", "rfd_200ms_t",
    "bs_1rm_bw_t", "pc_1rm_bw_t", "bp_1rm_bw_t", "hpc_1rm_bw_t",
    "jump_height_z", "peak_power_bm_z", "mrsi_z",
    "hsd_z", "player_load_z", "max_vel_z", "weight_z",
    "peak_force_bm_z", "peak_force_n_z", "rfd_100ms_z", "rfd_200ms_z",
    "bs_1rm_bw_z", "pc_1rm_bw_z", "bp_1rm_bw_z", "hpc_1rm_bw_z",
    "cmj_domain", "gps_domain", "bw_domain", "strength_domain", "weight_room_domain",
    "tsa_score", "tsa_rank", "rag", "missing_domains",
]
```

- [ ] **Step 6: Update renderer.py — build_history() signature and perch loop**

Replace the `build_history` function signature and add the perch history loop:

```python
def build_history(athlete_records, cmj_hist, gps_hist, bw_hist, imtp_hist, perch_hist, pop_stats):
    """
    Attaches *_history arrays to each athlete dict in athlete_records (in-place).
    pop_stats keys match snapshot raw column names.
    """
    from src.data import _normalize_name

    def _grp(df, col):
        return df.groupby(col) if not df.empty and col in df.columns else {}

    cmj_grp   = _grp(cmj_hist,   "forcedecks_id")
    imtp_grp  = _grp(imtp_hist,  "forcedecks_id")
    bw_grp    = _grp(bw_hist,    "name_normalized")
    gps_grp   = _grp(gps_hist,   "catapult_id")
    perch_grp = _grp(perch_hist, "forcedecks_id")

    for rec in athlete_records:
        fd_id     = rec.get("forcedecks_id")
        cat_id    = rec.get("catapult_id")
        name_norm = _normalize_name(rec.get("full_name", ""))

        # ── CMJ (unchanged) ──
        rec["cmj_history"] = []
        if fd_id and hasattr(cmj_grp, "groups") and fd_id in cmj_grp.groups:
            for _, row in cmj_grp.get_group(fd_id).iterrows():
                jh_t = _t_score_val(row.get("jump_height_cm"), pop_stats.get("jump_height_cm", {}))
                pp_t = _t_score_val(row.get("peak_power_bm"),  pop_stats.get("peak_power_bm", {}))
                mr_t = _t_score_val(row.get("mrsi"),           pop_stats.get("mrsi", {}))
                rec["cmj_history"].append({
                    "date":            str(row["test_date"])[:10],
                    "jump_height_cm":  _safe(row.get("jump_height_cm")),
                    "peak_power_bm":   _safe(row.get("peak_power_bm")),
                    "mrsi":            _safe(row.get("mrsi")),
                    "jump_height_t":   jh_t,
                    "peak_power_bm_t": pp_t,
                    "mrsi_t":          mr_t,
                    "cmj_domain_t":    _domain_t([jh_t, pp_t, mr_t]),
                })

        # ── IMTP (unchanged) ──
        rec["imtp_history"] = []
        if fd_id and hasattr(imtp_grp, "groups") and fd_id in imtp_grp.groups:
            for _, row in imtp_grp.get_group(fd_id).iterrows():
                pf_t  = _t_score_val(row.get("peak_force_bm"), pop_stats.get("peak_force_bm", {}))
                r1_t  = _t_score_val(row.get("rfd_100ms"),     pop_stats.get("rfd_100ms", {}))
                r2_t  = _t_score_val(row.get("rfd_200ms"),     pop_stats.get("rfd_200ms", {}))
                rec["imtp_history"].append({
                    "date":             str(row["test_date"])[:10],
                    "peak_force_n":     _safe(row.get("peak_force_n")),
                    "peak_force_bm":    _safe(row.get("peak_force_bm")),
                    "rfd_100ms":        _safe(row.get("rfd_100ms")),
                    "rfd_200ms":        _safe(row.get("rfd_200ms")),
                    "peak_force_bm_t":  pf_t,
                    "rfd_100ms_t":      r1_t,
                    "rfd_200ms_t":      r2_t,
                    "str_domain_t":     pf_t,
                })

        # ── Body Weight (unchanged) ──
        rec["bw_history"] = []
        if name_norm and hasattr(bw_grp, "groups") and name_norm in bw_grp.groups:
            for _, row in bw_grp.get_group(name_norm).iterrows():
                wt_t = _t_score_val(row.get("weight_kg"), pop_stats.get("weight_kg", {}))
                rec["bw_history"].append({
                    "date":        str(row["date"])[:10],
                    "weight_kg":   _safe(row.get("weight_kg")),
                    "weight_t":    wt_t,
                    "bw_domain_t": wt_t,
                })

        # ── GPS (unchanged) ──
        rec["gps_history"] = []
        if cat_id and hasattr(gps_grp, "groups") and cat_id in gps_grp.groups:
            df_rolled = _gps_rolling(gps_grp.get_group(cat_id))
            for _, row in df_rolled.iterrows():
                hsd = row.get("hsd_m")
                pl  = row.get("player_load")
                mv  = row.get("max_velocity_ms")
                hsd_t = _t_score_val(hsd, pop_stats.get("avg_hsd_m", {}))           if hsd is not None else None
                pl_t  = _t_score_val(pl,  pop_stats.get("avg_player_load", {}))     if pl  is not None else None
                mv_t  = _t_score_val(mv,  pop_stats.get("avg_max_velocity_ms", {})) if mv  is not None else None
                rec["gps_history"].append({
                    "date":            str(row["session_date"])[:10],
                    "hsd_m":           _safe(hsd) if hsd is not None else None,
                    "player_load":     _safe(pl)  if pl  is not None else None,
                    "max_velocity_ms": _safe(mv)  if mv  is not None else None,
                    "hsd_t":           hsd_t,
                    "player_load_t":   pl_t,
                    "max_vel_t":       mv_t,
                    "gps_domain_t":    _domain_t([hsd_t, pl_t, mv_t]),
                })

        # ── Perch / Weight Room ──
        rec["perch_history"] = []
        if fd_id and hasattr(perch_grp, "groups") and fd_id in perch_grp.groups:
            for _, row in perch_grp.get_group(fd_id).iterrows():
                bs  = row.get("bs_1rm_bw")
                pc  = row.get("pc_1rm_bw")
                bp  = row.get("bp_1rm_bw")
                hpc = row.get("hpc_1rm_bw")
                bs_t  = _t_score_val(bs,  pop_stats.get("bs_1rm_bw",  {}))
                pc_t  = _t_score_val(pc,  pop_stats.get("pc_1rm_bw",  {}))
                bp_t  = _t_score_val(bp,  pop_stats.get("bp_1rm_bw",  {}))
                hpc_t = _t_score_val(hpc, pop_stats.get("hpc_1rm_bw", {}))
                rec["perch_history"].append({
                    "date":        str(row["test_date"])[:10],
                    "bs_1rm_bw":   _safe(bs),
                    "pc_1rm_bw":   _safe(pc),
                    "bp_1rm_bw":   _safe(bp),
                    "hpc_1rm_bw":  _safe(hpc),
                    "bs_1rm_bw_t": bs_t,
                    "pc_1rm_bw_t": pc_t,
                    "bp_1rm_bw_t": bp_t,
                    "hpc_1rm_bw_t":hpc_t,
                    "wr_domain_t": _domain_t([t for t in [bs_t, pc_t, bp_t, hpc_t] if t is not None]),
                })
```

- [ ] **Step 7: Update renderer.py — render() signature, team_avg, perch_count**

Replace `render()` signature and update the body:

```python
def render(
    df_scored: pd.DataFrame,
    pop_stats: dict,
    cmj_hist: pd.DataFrame,
    gps_hist: pd.DataFrame,
    bw_hist: pd.DataFrame,
    imtp_hist: pd.DataFrame,
    perch_hist: pd.DataFrame,
    label: str,
    start_date: str,
    end_date: str,
) -> str:
```

Update the `build_history` call inside `render()`:

```python
build_history(records, cmj_hist, gps_hist, bw_hist, imtp_hist, perch_hist, pop_stats)
```

Update `numeric_cols` and `team_avg`:

```python
numeric_cols = [
    "jump_height_cm", "peak_power_bm", "mrsi",
    "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms", "weight_kg",
    "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms",
    "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw",
]
```

Add `perch_count` alongside the other count variables:

```python
perch_count = int(df["bs_1rm_bw"].notna().sum()) if "bs_1rm_bw" in df.columns else 0
```

Add `perch_count=perch_count` to the `tmpl.render(...)` call.

- [ ] **Step 8: Run tests to verify they pass**

```
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add src/renderer.py tests/test_history.py
git commit -m "feat: renderer.py — Perch history, 5-domain build_history, perch_count"
```

---

## Task 8: generate_report.py — update CLI

**Files:**
- Modify: `generate_report.py`

- [ ] **Step 1: Update generate_report.py**

Replace the `main()` function body with:

```python
def main():
    parser = argparse.ArgumentParser(description="Generate Football Performance Report")
    parser.add_argument("--start",  required=True,  help="Period start date (YYYY-MM-DD)")
    parser.add_argument("--end",    required=True,  help="Period end date   (YYYY-MM-DD)")
    parser.add_argument("--label",  default="Report", help="Report label (e.g. 'Spring 2026')")
    parser.add_argument("--output", default=None,   help="Override output file path")
    args = parser.parse_args()

    print(f"Loading data: {args.start} to {args.end} ...")
    df = merge_all(args.start, args.end)
    print(f"  Athletes loaded:    {len(df)}")
    print(f"  CMJ coverage:       {df['jump_height_cm'].notna().sum()}/{len(df)}")
    print(f"  GPS coverage:       {df['avg_hsd_m'].notna().sum()}/{len(df)}")
    print(f"  BW  coverage:       {df['weight_kg'].notna().sum()}/{len(df)}")
    print(f"  IMTP coverage:      {df['peak_force_bm'].notna().sum()}/{len(df)}")
    print(f"  Perch coverage:     {df['bs_1rm_bw'].notna().sum()}/{len(df)}" if "bs_1rm_bw" in df.columns else "  Perch:             no data")

    print("Scoring ...")
    df_scored, pop_stats = score(df)
    rag_counts = df_scored["rag"].value_counts()
    print(f"  Green: {rag_counts.get('green', 0)}  Amber: {rag_counts.get('amber', 0)}  Red: {rag_counts.get('red', 0)}")

    print("Loading history ...")
    from src.data import load_cmj_history, load_imtp_history, load_bw_history, load_gps_history, load_perch_history
    cmj_hist   = load_cmj_history(args.start, args.end)
    imtp_hist  = load_imtp_history(args.start, args.end)
    bw_hist    = load_bw_history(args.end)
    gps_hist   = load_gps_history(args.start, args.end)
    perch_hist = load_perch_history(args.start, args.end)
    print(f"  CMJ tests:      {len(cmj_hist)}")
    print(f"  IMTP tests:     {len(imtp_hist)}")
    print(f"  BW entries:     {len(bw_hist)}")
    print(f"  GPS sessions:   {len(gps_hist)}")
    print(f"  Perch sessions: {len(perch_hist)}")

    print("Rendering HTML ...")
    html = render(df_scored, pop_stats, cmj_hist, gps_hist, bw_hist, imtp_hist, perch_hist,
                  args.label, args.start, args.end)

    if args.output:
        out_path = Path(args.output)
    else:
        safe_label = args.label.replace(" ", "_").replace("/", "-")
        out_path = OUTPUT_DIR / f"{safe_label}_{args.end}.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"\nReport saved: {out_path}")
```

- [ ] **Step 2: Run the report to verify end-to-end (no Perch data yet)**

```bash
python generate_report.py --start 2025-09-01 --end 2026-03-28 --label "Spring 2026"
```

Expected: runs without error, prints "Perch sessions: 0", saves HTML.

- [ ] **Step 3: Commit**

```bash
git add generate_report.py
git commit -m "feat: generate_report.py — load perch_hist, 5-domain render call"
```

---

## Task 9: templates/report.html.j2 — Weight Room UI

**Files:**
- Modify: `templates/report.html.j2`

This task has no automated test — verify visually by opening the generated HTML.

### 9a — TEAM_AVG, spider, and table column

- [ ] **Step 1: Add perch entries to TEAM_AVG**

Find the TEAM_AVG constant block (near `rfd_200ms` line ~242) and add 4 lines after `rfd_200ms`:

```javascript
  bs_1rm_bw:   {{ team_avg.bs_1rm_bw  | default(0) | round(2) }},
  pc_1rm_bw:   {{ team_avg.pc_1rm_bw  | default(0) | round(2) }},
  bp_1rm_bw:   {{ team_avg.bp_1rm_bw  | default(0) | round(2) }},
  hpc_1rm_bw:  {{ team_avg.hpc_1rm_bw | default(0) | round(2) }},
```

- [ ] **Step 2: Add "Weight Room" to spider**

Find SPIDER_LABELS and SPIDER_T_KEYS (lines ~246-253) and update:

```javascript
const SPIDER_LABELS = [
  "Jump Height", "Peak Power/BM", "mRSI",
  "High Speed Dist", "Player Load", "Max Velocity", "Body Weight", "Peak Force/BM",
  "Weight Room"
];
const SPIDER_T_KEYS = [
  "jump_height_t","peak_power_bm_t","mrsi_t",
  "hsd_t","player_load_t","max_vel_t","weight_t","peak_force_bm_t",
  "weight_room_domain"
];
```

- [ ] **Step 3: Add Perch data coverage pill**

Find the IMTP pill line (~181) and add after it:

```html
<span class="pill {% if perch_count > 0 %}ok{% endif %}">Perch {{ perch_count }} athletes</span>
```

Also add `{{ perch_count }}` variable to the template — it's passed from `render()` in Task 7.

- [ ] **Step 4: Add Weight Room column to table header**

Find the table header row with `<th onclick="sortTable('strength_domain')` (line ~215) and add after it:

```html
<th onclick="sortTable('weight_room_domain')" id="th-weight_room_domain">Wt Rm</th>
```

- [ ] **Step 5: Update colspan from 9 to 10**

Find the line with `colspan="9"` (line ~292):

```html
<td colspan="9" class="profile-panel" id="panel-${a.forcedecks_id}"></td>
```

Change to `colspan="10"`.

- [ ] **Step 6: Add Weight Room cell to renderRow()**

Find the `strengthHtml` line (~275) and add after:

```javascript
const wrHtml = a.weight_room_domain != null ? fmt(a.weight_room_domain) : '<span class="val-na">—</span>';
```

Find the `<td class="domain-cell">${strengthHtml}</td>` line (~288) and add after:

```javascript
<td class="domain-cell">${wrHtml}</td>
```

### 9b — Profile panel Weight Room section

- [ ] **Step 7: Add Weight Room section to buildMetricsTable()**

Find the closing `]};` after the `Strength (IMTP)` section (~316) and add before it:

```javascript
    { section: "Weight Room (Perch)", metrics: [
      { label: "Back Squat 1RM/BW",       raw: fmt(a.bs_1rm_bw,  2), z: a.bs_1rm_bw_z,  t: a.bs_1rm_bw_t,  avg: fmt(TEAM_AVG.bs_1rm_bw,  2) },
      { label: "Power Clean 1RM/BW",      raw: fmt(a.pc_1rm_bw,  2), z: a.pc_1rm_bw_z,  t: a.pc_1rm_bw_t,  avg: fmt(TEAM_AVG.pc_1rm_bw,  2) },
      { label: "Bench Press 1RM/BW",      raw: fmt(a.bp_1rm_bw,  2), z: a.bp_1rm_bw_z,  t: a.bp_1rm_bw_t,  avg: fmt(TEAM_AVG.bp_1rm_bw,  2) },
      { label: "Hang Power Clean 1RM/BW", raw: fmt(a.hpc_1rm_bw, 2), z: a.hpc_1rm_bw_z, t: a.hpc_1rm_bw_t, avg: fmt(TEAM_AVG.hpc_1rm_bw, 2) },
    ]},
```

### 9c — Trend chart Weight Room support

- [ ] **Step 8: Add Weight Room to TREND_DOMAIN_CFG**

Find `TREND_DOMAIN_CFG` array (~365) and add entry after IMTP:

```javascript
  { key: "wr", histKey: "perch_history", domainT: "wr_domain_t", label: "Weight Room", color: "#a855f7" },
```

- [ ] **Step 9: Add perch detail metrics to TREND_DETAIL_METRICS**

Find `TREND_DETAIL_METRICS` object (~514) and add `wr` entry:

```javascript
  wr: [
    { key: "bs_1rm_bw",  tKey: "bs_1rm_bw_t",  label: "Back Squat 1RM/BW",       color: "#c084fc", dash: [] },
    { key: "pc_1rm_bw",  tKey: "pc_1rm_bw_t",  label: "Power Clean 1RM/BW",      color: "#a855f7", dash: [] },
    { key: "bp_1rm_bw",  tKey: "bp_1rm_bw_t",  label: "Bench Press 1RM/BW",      color: "#7e22ce", dash: [5,3] },
    { key: "hpc_1rm_bw", tKey: "hpc_1rm_bw_t", label: "Hang Power Clean 1RM/BW", color: "#e879f9", dash: [2,4] },
  ],
```

- [ ] **Step 10: Generate report and verify UI**

```bash
python generate_report.py --start 2025-09-01 --end 2026-03-28 --label "Spring 2026"
```

Open `output/Spring_2026_2026-03-28.html` in a browser. Verify:
- Radar has 9 axes; "Weight Room" axis visible (at 50.0 for all athletes when no Perch data)
- Table has "Wt Rm" column showing `—` for all athletes (no Perch data yet)
- Profile panel has "Weight Room (Perch)" section (all `—`)
- Trend chart has "Weight Room" domain button (disabled when no history)
- No JS console errors

- [ ] **Step 11: Run full test suite one final time**

```
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 12: Commit**

```bash
git add templates/report.html.j2
git commit -m "feat: template — Weight Room axis (radar, table, profile panel, trend chart)"
```

---

## End-to-End Verification (with real Perch data)

After Task 9 is complete and the Perch DB is populated (Task 3):

```bash
python generate_report.py --start 2025-09-01 --end 2026-03-28 --label "Spring 2026"
```

Open the report and confirm:
- Athletes with Perch data show Weight Room scores (not `—`) in table and radar
- Athletes without Perch data show `—` and "Weight Room" in their missing_domains note
- Clicking "Weight Room" trend button shows history for athletes with multiple Perch sessions
- Clicking individual exercise lines in the detail chart shows 1RM/BW trends per exercise
- TSA ranks shift appropriately with the 5th domain included

---

## What Is Not Built (flag for future)

- **Per-test BW normalization** — all history points use snapshot end_date BW. If athlete weight changes significantly mid-season, the historical ratios are slightly off. Fix: join each Perch history point to the nearest BW CSV entry by date.
- **Perch sets data** — `/sets` endpoint has per-set velocity/power data for periodization analysis. Not included in TSA; design separately.
- **Weight Room trend breaks** — GPS uses a 21-day gap sentinel for off-season breaks. Perch history doesn't yet insert null sentinels for long gaps; add if needed for chart clarity.
