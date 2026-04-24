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
