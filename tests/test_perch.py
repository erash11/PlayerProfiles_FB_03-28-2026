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


def test_ensure_schema_creates_table(tmp_path):
    """ensure_schema() creates perch_1rm with correct columns."""
    tmp = str(tmp_path / "perch.duckdb")
    conn = duckdb.connect(tmp)
    from src.perch_ingest import ensure_schema
    ensure_schema(conn)
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='perch_1rm'"
    ).df()
    col_names = set(cols["column_name"].tolist())
    conn.close()
    assert {"name_normalized", "perch_user_id", "exercise", "one_rm_lbs", "test_date"} <= col_names


def test_upsert_rows_inserts_and_deduplicates(tmp_path):
    """upsert_rows() handles duplicate (name, exercise, date) by keeping latest."""
    tmp = str(tmp_path / "perch.duckdb")
    conn = duckdb.connect(tmp)
    from src.perch_ingest import ensure_schema, upsert_rows
    ensure_schema(conn)

    rows = [
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 315.0, "test_date": "2025-10-01"},
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 320.0, "test_date": "2025-10-01"},  # same key
        {"name_normalized": "bob jones",  "perch_user_id": "u2",
         "exercise": "Bench Press", "one_rm_lbs": 225.0, "test_date": "2025-10-01"},
    ]
    upsert_rows(conn, rows)

    count = conn.execute("SELECT COUNT(*) FROM perch_1rm").fetchone()[0]
    alice_1rm = conn.execute(
        "SELECT one_rm_lbs FROM perch_1rm WHERE name_normalized='alice smith'"
    ).fetchone()[0]
    conn.close()

    assert count == 2, f"Expected 2 rows (deduped), got {count}"
    assert alice_1rm == pytest.approx(320.0), "Later value should overwrite earlier"


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_perch_db(tmp_path, rows):
    """Helper: create a temp perch.duckdb with given rows."""
    db = str(tmp_path / "perch.duckdb")
    conn = duckdb.connect(db)
    from src.perch_ingest import ensure_schema, upsert_rows
    ensure_schema(conn)
    upsert_rows(conn, rows)
    conn.close()
    return db


def _make_roster_csv(tmp_path):
    import csv
    p = str(tmp_path / "roster.csv")
    with open(p, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["full_name", "jersey_number", "position", "catapult_id", "forcedecks_id"]
        )
        writer.writeheader()
        writer.writerow({"full_name": "Alice Smith", "jersey_number": "", "position": "WR",
                         "catapult_id": "c1", "forcedecks_id": "fd1"})
        writer.writerow({"full_name": "Bob Jones", "jersey_number": "", "position": "OL",
                         "catapult_id": "c2", "forcedecks_id": "fd2"})
    return p


def _make_bw_csv(tmp_path):
    p = str(tmp_path / "bw.csv")
    with open(p, "w") as f:
        f.write("DATE,NAME,WEIGHT,POS\n")
        f.write('10/01/2025,"Smith, Alice",150,WR\n')  # 150 lbs
        f.write('10/01/2025,"Jones, Bob",220,OL\n')    # 220 lbs
    return p


# ── load_perch() tests ────────────────────────────────────────────────────────

def test_load_perch_returns_normalized_ratios(tmp_path):
    """1RM / BW ratios computed correctly from cache."""
    from unittest.mock import patch

    db      = _make_perch_db(tmp_path, [
        # Alice: BS 300 lbs / 150 lbs BW = 2.0
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 300.0, "test_date": "2025-10-15"},
    ])
    roster  = _make_roster_csv(tmp_path)
    bw      = _make_bw_csv(tmp_path)

    from src.data import load_perch
    with patch("src.data.PERCH_DB", db), \
         patch("src.data.ROSTER_CSV", roster), \
         patch("src.data.BODYWEIGHT_CSV", bw):
        df = load_perch("2025-09-01", "2026-03-28")

    assert "bs_1rm_bw" in df.columns
    alice = df[df["forcedecks_id"] == "fd1"]
    assert len(alice) == 1
    assert alice["bs_1rm_bw"].iloc[0] == pytest.approx(2.0, rel=1e-4)

    # Bob has no Perch data — should not appear
    assert "fd2" not in df["forcedecks_id"].values


def test_load_perch_missing_db_returns_empty():
    """If perch.duckdb doesn't exist, load_perch() returns empty DataFrame."""
    from unittest.mock import patch
    from src.data import load_perch

    with patch("src.data.PERCH_DB", "/nonexistent/path/perch.duckdb"):
        df = load_perch("2025-09-01", "2026-03-28")

    assert df.empty or df["bs_1rm_bw"].isna().all()
    assert "forcedecks_id" in df.columns


# ── load_perch_history() tests ────────────────────────────────────────────────

def test_merge_all_includes_perch_columns(tmp_path):
    """merge_all() result has bs_1rm_bw column (NaN for all when no Perch DB)."""
    from unittest.mock import patch
    import pandas as pd
    from src.data import merge_all

    roster = _make_roster_csv(tmp_path)
    bw     = _make_bw_csv(tmp_path)

    empty_fp   = pd.DataFrame(columns=["forcedecks_id", "jump_height_cm", "peak_power_bm", "mrsi"])
    empty_gps  = pd.DataFrame(columns=["catapult_id", "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms"])
    empty_imtp = pd.DataFrame(columns=["forcedecks_id", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    with patch("src.data.PERCH_DB", "/nonexistent/perch.duckdb"), \
         patch("src.data.ROSTER_CSV", roster), \
         patch("src.data.BODYWEIGHT_CSV", bw), \
         patch("src.data.load_cmj",  return_value=empty_fp), \
         patch("src.data.load_gps",  return_value=empty_gps), \
         patch("src.data.load_imtp", return_value=empty_imtp):
        df = merge_all("2025-09-01", "2026-03-28")

    assert "bs_1rm_bw" in df.columns, "merge_all() must include bs_1rm_bw"
    assert df["bs_1rm_bw"].isna().all(), "No Perch DB → all NaN"


def test_load_perch_history_multiple_dates(tmp_path):
    """History loader returns one row per date (not just most recent)."""
    from unittest.mock import patch

    db     = _make_perch_db(tmp_path, [
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 280.0, "test_date": "2025-09-01"},
        {"name_normalized": "alice smith", "perch_user_id": "u1",
         "exercise": "Back Squat", "one_rm_lbs": 300.0, "test_date": "2025-10-15"},
    ])
    roster = _make_roster_csv(tmp_path)
    bw     = _make_bw_csv(tmp_path)

    from src.data import load_perch_history
    with patch("src.data.PERCH_DB", db), \
         patch("src.data.ROSTER_CSV", roster), \
         patch("src.data.BODYWEIGHT_CSV", bw):
        df = load_perch_history("2025-09-01", "2026-03-28")

    alice = df[df["forcedecks_id"] == "fd1"]
    assert len(alice) == 2, f"Expected 2 history rows, got {len(alice)}"
    dates = alice["test_date"].astype(str).str[:10].tolist()
    assert dates == ["2025-09-01", "2025-10-15"]
