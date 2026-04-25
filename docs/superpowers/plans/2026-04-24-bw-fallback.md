# BW Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 12 roster athletes who have no BW CSV match by falling back to `"Bodyweight in Kilograms"` from ForceDecks `raw_tests`, restoring their BW domain score and Perch 1RM/BW normalization.

**Architecture:** Two new private functions added to `src/data.py` — `_load_fd_bw()` queries `raw_tests` for the most recent body weight per athlete; `_load_bw_combined()` coalesces CSV (primary) and FD (fallback) sources. `merge_all()` is updated to use the combined loader. `load_perch()` and `load_perch_history()` apply the FD fallback directly after their CSV BW join. No other files are touched.

**Tech Stack:** Python, pandas (`combine_first` for coalescing), DuckDB, pytest with `unittest.mock.patch`

---

## File Map

| File | Change |
|------|--------|
| `src/data.py` | Add `_load_fd_bw()`, `_load_bw_combined()`; update `merge_all()`, `load_perch()`, `load_perch_history()` |
| `tests/test_perch.py` | Add `_make_fd_db()` helper + 5 new tests |

---

### Task 1: Add `_load_fd_bw()` with tests

**Files:**
- Modify: `src/data.py` (after `_load_bw_lbs()` at line 396)
- Modify: `tests/test_perch.py` (add helper + 2 tests)

- [ ] **Step 1: Add `_make_fd_db()` test helper to `tests/test_perch.py`**

Add after the existing `_make_bw_csv()` helper (around line 91):

```python
def _make_fd_db(tmp_path, rows):
    """Helper: create a temp forceplate.db with raw_tests rows."""
    db = str(tmp_path / "forceplate.db")
    conn = duckdb.connect(db)
    conn.execute("""
        CREATE TABLE raw_tests (
            test_id VARCHAR NOT NULL,
            athlete_id VARCHAR NOT NULL,
            athlete_name VARCHAR,
            position VARCHAR,
            position_group VARCHAR,
            test_date DATE,
            metric_name VARCHAR NOT NULL,
            metric_value DOUBLE,
            metric_unit VARCHAR,
            pulled_at TIMESTAMP DEFAULT now(),
            PRIMARY KEY (test_id, metric_name)
        )
    """)
    for row in rows:
        conn.execute(
            "INSERT INTO raw_tests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, now())",
            [row["test_id"], row["athlete_id"], row.get("athlete_name", ""),
             None, None, row["test_date"], row["metric_name"], row["metric_value"], "kg"]
        )
    conn.close()
    return db
```

- [ ] **Step 2: Write the failing tests for `_load_fd_bw()`**

Add at the end of `tests/test_perch.py`:

```python
# ── _load_fd_bw() tests ───────────────────────────────────────────────────────

def test_load_fd_bw_returns_most_recent(tmp_path):
    """_load_fd_bw returns most recent weight per athlete within date range."""
    db = _make_fd_db(tmp_path, [
        {"test_id": "t1", "athlete_id": "fd1", "test_date": "2025-09-01",
         "metric_name": "Bodyweight in Kilograms", "metric_value": 80.0},
        {"test_id": "t2", "athlete_id": "fd1", "test_date": "2025-10-15",
         "metric_name": "Bodyweight in Kilograms", "metric_value": 82.0},
        {"test_id": "t3", "athlete_id": "fd2", "test_date": "2025-09-01",
         "metric_name": "Bodyweight in Kilograms", "metric_value": 110.0},
    ])
    from src.data import _load_fd_bw
    from unittest.mock import patch
    with patch("src.data.FORCEPLATE_DB", db):
        df = _load_fd_bw("2025-09-01", "2026-03-28")

    assert len(df) == 2
    fd1 = df[df["forcedecks_id"] == "fd1"]
    assert fd1["weight_kg"].iloc[0] == pytest.approx(82.0)
    fd2 = df[df["forcedecks_id"] == "fd2"]
    assert fd2["weight_kg"].iloc[0] == pytest.approx(110.0)


def test_load_fd_bw_unreachable_returns_empty():
    """_load_fd_bw returns empty DataFrame with correct columns if DB is unreachable."""
    from src.data import _load_fd_bw
    from unittest.mock import patch
    with patch("src.data.FORCEPLATE_DB", "/nonexistent/path.db"):
        df = _load_fd_bw("2025-09-01", "2026-03-28")

    assert df.empty
    assert "forcedecks_id" in df.columns
    assert "weight_kg" in df.columns
```

- [ ] **Step 3: Run tests to verify they fail**

```
pytest tests/test_perch.py::test_load_fd_bw_returns_most_recent tests/test_perch.py::test_load_fd_bw_unreachable_returns_empty -v
```

Expected: `ImportError` or `AttributeError` — `_load_fd_bw` not yet defined.

- [ ] **Step 4: Add `_load_fd_bw()` to `src/data.py`**

Add after `_load_bw_lbs()` (after line 403 in the current file):

```python
def _load_fd_bw(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Most recent ForceDecks body weight per athlete within [start_date, end_date].
    Returns: forcedecks_id, weight_kg (kg — native FD unit).
    Returns empty DataFrame if DB is unreachable or has no matching rows.
    """
    try:
        conn = duckdb.connect(str(FORCEPLATE_DB), read_only=True)
        result = conn.execute("""
            SELECT athlete_id AS forcedecks_id, metric_value AS weight_kg
            FROM (
                SELECT athlete_id, metric_value,
                       ROW_NUMBER() OVER (PARTITION BY athlete_id ORDER BY test_date DESC) AS rn
                FROM raw_tests
                WHERE metric_name = 'Bodyweight in Kilograms'
                  AND test_date BETWEEN ? AND ?
            ) t
            WHERE rn = 1
        """, [start_date, end_date]).df()
        conn.close()
        return result
    except Exception:
        return pd.DataFrame(columns=["forcedecks_id", "weight_kg"])
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_perch.py::test_load_fd_bw_returns_most_recent tests/test_perch.py::test_load_fd_bw_unreachable_returns_empty -v
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```
git add src/data.py tests/test_perch.py
git commit -m "feat: data.py — add _load_fd_bw() with ForceDecks BW fallback"
```

---

### Task 2: Add `_load_bw_combined()` with tests

**Files:**
- Modify: `src/data.py` (add function after `_load_fd_bw()`)
- Modify: `tests/test_perch.py` (add 2 tests)

- [ ] **Step 1: Write the failing tests for `_load_bw_combined()`**

Add at the end of `tests/test_perch.py`:

```python
# ── _load_bw_combined() tests ─────────────────────────────────────────────────

def test_load_bw_combined_csv_wins(tmp_path):
    """_load_bw_combined: athlete in CSV gets CSV weight, not FD weight."""
    fd_db = _make_fd_db(tmp_path, [
        {"test_id": "t1", "athlete_id": "fd1", "test_date": "2025-10-01",
         "metric_name": "Bodyweight in Kilograms", "metric_value": 99.0},  # should be ignored
    ])
    roster = _make_roster_csv(tmp_path)
    bw     = _make_bw_csv(tmp_path)  # Alice = 150 lbs → 68.04 kg

    from src.data import _load_bw_combined
    from unittest.mock import patch
    with patch("src.data.FORCEPLATE_DB", fd_db), \
         patch("src.data.ROSTER_CSV", roster), \
         patch("src.data.BODYWEIGHT_CSV", bw):
        df = _load_bw_combined("2025-09-01", "2026-03-28")

    alice = df[df["name_normalized"] == "alice smith"]
    assert len(alice) == 1
    assert alice["weight_kg"].iloc[0] == pytest.approx(150 * 0.453592, rel=1e-4)


def test_load_bw_combined_fd_fills_csv_gap(tmp_path):
    """_load_bw_combined: athlete missing from CSV gets FD weight."""
    bw_bob_only = str(tmp_path / "bw_bob_only.csv")
    with open(bw_bob_only, "w") as f:
        f.write("DATE,NAME,WEIGHT,POS\n")
        f.write('10/01/2025,"Jones, Bob",220,OL\n')  # Alice not in CSV

    fd_db = _make_fd_db(tmp_path, [
        {"test_id": "t1", "athlete_id": "fd1", "test_date": "2025-10-01",
         "metric_name": "Bodyweight in Kilograms", "metric_value": 75.0},
    ])
    roster = _make_roster_csv(tmp_path)  # fd1=Alice, fd2=Bob

    from src.data import _load_bw_combined
    from unittest.mock import patch
    with patch("src.data.FORCEPLATE_DB", fd_db), \
         patch("src.data.ROSTER_CSV", roster), \
         patch("src.data.BODYWEIGHT_CSV", bw_bob_only):
        df = _load_bw_combined("2025-09-01", "2026-03-28")

    alice = df[df["name_normalized"] == "alice smith"]
    assert len(alice) == 1
    assert alice["weight_kg"].iloc[0] == pytest.approx(75.0, rel=1e-4)
    bob = df[df["name_normalized"] == "bob jones"]
    assert len(bob) == 1
    assert bob["weight_kg"].iloc[0] == pytest.approx(220 * 0.453592, rel=1e-4)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_perch.py::test_load_bw_combined_csv_wins tests/test_perch.py::test_load_bw_combined_fd_fills_csv_gap -v
```

Expected: `ImportError` or `AttributeError` — `_load_bw_combined` not yet defined.

- [ ] **Step 3: Add `_load_bw_combined()` to `src/data.py`**

Add immediately after `_load_fd_bw()`:

```python
def _load_bw_combined(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Body weight per athlete: CSV primary, ForceDecks raw_tests fallback.
    Returns: name_normalized, weight_kg
    CSV value wins; FD fills gaps for roster athletes missing from CSV.
    """
    csv_bw = load_bodyweight(end_date)  # name_normalized, weight_kg

    fd_bw = _load_fd_bw(start_date, end_date)
    if fd_bw.empty:
        return csv_bw

    roster = pd.read_csv(ROSTER_CSV)
    roster["name_normalized"] = roster["full_name"].apply(_normalize_name)
    fd_named = fd_bw.merge(
        roster[["forcedecks_id", "name_normalized"]], on="forcedecks_id", how="inner"
    )[["name_normalized", "weight_kg"]].rename(columns={"weight_kg": "weight_kg_fd"})

    combined = csv_bw.merge(fd_named, on="name_normalized", how="outer")
    combined["weight_kg"] = combined["weight_kg"].combine_first(combined["weight_kg_fd"])
    return (
        combined[["name_normalized", "weight_kg"]]
        .dropna(subset=["weight_kg"])
        .reset_index(drop=True)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_perch.py::test_load_bw_combined_csv_wins tests/test_perch.py::test_load_bw_combined_fd_fills_csv_gap -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```
git add src/data.py tests/test_perch.py
git commit -m "feat: data.py — add _load_bw_combined() coalescing CSV + FD body weight sources"
```

---

### Task 3: Update `merge_all()` with test

**Files:**
- Modify: `src/data.py` (`merge_all()` function, around line 538)
- Modify: `tests/test_perch.py` (add 1 test)

- [ ] **Step 1: Write the failing test**

Add at the end of `tests/test_perch.py`:

```python
# ── merge_all() BW fallback test ──────────────────────────────────────────────

def test_merge_all_bw_fallback_fills_missing_csv_athletes(tmp_path):
    """merge_all(): athlete missing from BW CSV gets weight_kg from ForceDecks fallback."""
    bw_bob_only = str(tmp_path / "bw_bob_only.csv")
    with open(bw_bob_only, "w") as f:
        f.write("DATE,NAME,WEIGHT,POS\n")
        f.write('10/01/2025,"Jones, Bob",220,OL\n')  # Alice not in CSV

    fd_db = _make_fd_db(tmp_path, [
        {"test_id": "t1", "athlete_id": "fd1", "test_date": "2025-10-01",
         "metric_name": "Bodyweight in Kilograms", "metric_value": 75.0},
    ])
    roster = _make_roster_csv(tmp_path)  # fd1=Alice, fd2=Bob

    from src.data import merge_all
    from unittest.mock import patch
    import pandas as pd

    empty_cmj  = pd.DataFrame(columns=["forcedecks_id", "jump_height_cm", "peak_power_bm", "mrsi"])
    empty_gps  = pd.DataFrame(columns=["catapult_id", "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms"])
    empty_imtp = pd.DataFrame(columns=["forcedecks_id", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    with patch("src.data.FORCEPLATE_DB", fd_db), \
         patch("src.data.ROSTER_CSV", roster), \
         patch("src.data.BODYWEIGHT_CSV", bw_bob_only), \
         patch("src.data.PERCH_DB", "/nonexistent/perch.duckdb"), \
         patch("src.data.load_cmj",  return_value=empty_cmj), \
         patch("src.data.load_gps",  return_value=empty_gps), \
         patch("src.data.load_imtp", return_value=empty_imtp):
        df = merge_all("2025-09-01", "2026-03-28")

    alice = df[df["forcedecks_id"] == "fd1"]
    assert alice["weight_kg"].notna().all(), "Alice should have FD BW fallback weight"
    assert alice["weight_kg"].iloc[0] == pytest.approx(75.0, rel=1e-4)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_perch.py::test_merge_all_bw_fallback_fills_missing_csv_athletes -v
```

Expected: FAIL — Alice's `weight_kg` is NaN because `merge_all` still calls `load_bodyweight`.

- [ ] **Step 3: Update `merge_all()` in `src/data.py`**

In `merge_all()` (around line 546), replace:

```python
    bw    = load_bodyweight(end_date)
```

with:

```python
    bw    = _load_bw_combined(start_date, end_date)
```

No other changes needed — the merge on `name_normalized` stays the same.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_perch.py::test_merge_all_bw_fallback_fills_missing_csv_athletes -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```
pytest -v
```

Expected: all 26 prior tests still PASS, plus the new test.

- [ ] **Step 6: Commit**

```
git add src/data.py tests/test_perch.py
git commit -m "feat: data.py — merge_all() uses _load_bw_combined() for BW CSV fallback"
```

---

### Task 4: Update `load_perch()` and `load_perch_history()` with test

**Files:**
- Modify: `src/data.py` (`load_perch()` around line 406, `load_perch_history()` around line 475)
- Modify: `tests/test_perch.py` (add 1 test)

- [ ] **Step 1: Write the failing test**

Add at the end of `tests/test_perch.py`:

```python
# ── load_perch() BW fallback test ─────────────────────────────────────────────

def test_load_perch_bw_fallback_computes_ratio_for_missing_csv_athlete(tmp_path):
    """load_perch(): athlete not in BW CSV gets 1RM/BW ratio via FD BW fallback."""
    bw_bob_only = str(tmp_path / "bw_bob_only.csv")
    with open(bw_bob_only, "w") as f:
        f.write("DATE,NAME,WEIGHT,POS\n")
        f.write('10/01/2025,"Jones, Bob",220,OL\n')  # Alice not in CSV

    perch_db = _make_perch_db(tmp_path, [
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 225.0, "test_date": "2025-10-15"},
    ])
    # Alice BW in FD: 75 kg = 165.35 lbs → BS ratio = 225 / 165.35 ≈ 1.361
    fd_db = _make_fd_db(tmp_path, [
        {"test_id": "t1", "athlete_id": "fd1", "test_date": "2025-10-01",
         "metric_name": "Bodyweight in Kilograms", "metric_value": 75.0},
    ])
    roster = _make_roster_csv(tmp_path)  # fd1=Alice, fd2=Bob

    from src.data import load_perch
    from unittest.mock import patch
    with patch("src.data.PERCH_DB", perch_db), \
         patch("src.data.FORCEPLATE_DB", fd_db), \
         patch("src.data.ROSTER_CSV", roster), \
         patch("src.data.BODYWEIGHT_CSV", bw_bob_only):
        df = load_perch("2025-09-01", "2026-03-28")

    alice = df[df["forcedecks_id"] == "fd1"]
    assert len(alice) == 1
    assert alice["bs_1rm_bw"].notna().all(), "Alice should have bs_1rm_bw via FD BW fallback"
    expected = 225.0 / (75.0 / 0.453592)  # 225 lbs / 165.35 lbs ≈ 1.361
    assert alice["bs_1rm_bw"].iloc[0] == pytest.approx(expected, rel=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_perch.py::test_load_perch_bw_fallback_computes_ratio_for_missing_csv_athlete -v
```

Expected: FAIL — Alice's `bs_1rm_bw` is NaN because BW join by `name_normalized` misses her.

- [ ] **Step 3: Update `load_perch()` in `src/data.py`**

In `load_perch()`, after the line:

```python
    bw = _load_bw_lbs(end_date)
    pivoted = pivoted.merge(bw, on="name_normalized", how="left")
```

add:

```python
    fd_bw = _load_fd_bw(start_date, end_date)
    if not fd_bw.empty:
        fd_bw_lbs = fd_bw.assign(weight_lbs_fd=fd_bw["weight_kg"] / 0.453592)[["forcedecks_id", "weight_lbs_fd"]]
        pivoted = pivoted.merge(fd_bw_lbs, on="forcedecks_id", how="left")
        pivoted["weight_lbs"] = pivoted["weight_lbs"].combine_first(pivoted["weight_lbs_fd"])
        pivoted = pivoted.drop(columns=["weight_lbs_fd"])
```

- [ ] **Step 4: Apply the same change to `load_perch_history()` in `src/data.py`**

In `load_perch_history()`, after:

```python
    bw = _load_bw_lbs(end_date)
    pivoted = pivoted.merge(bw, on="name_normalized", how="left")
```

add:

```python
    fd_bw = _load_fd_bw(start_date, end_date)
    if not fd_bw.empty:
        fd_bw_lbs = fd_bw.assign(weight_lbs_fd=fd_bw["weight_kg"] / 0.453592)[["forcedecks_id", "weight_lbs_fd"]]
        pivoted = pivoted.merge(fd_bw_lbs, on="forcedecks_id", how="left")
        pivoted["weight_lbs"] = pivoted["weight_lbs"].combine_first(pivoted["weight_lbs_fd"])
        pivoted = pivoted.drop(columns=["weight_lbs_fd"])
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_perch.py::test_load_perch_bw_fallback_computes_ratio_for_missing_csv_athlete -v
```

Expected: PASS.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```
pytest -v
```

Expected: all prior tests still PASS plus the new test. Total should be 27+ tests passing.

- [ ] **Step 7: Commit**

```
git add src/data.py tests/test_perch.py
git commit -m "feat: data.py — load_perch/history use FD BW fallback for athletes missing CSV match"
```
