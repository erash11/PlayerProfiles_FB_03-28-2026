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
_STAT_USER_ID_FIELD  = "user_id"    # ⚠ confirm
_STAT_EXERCISE_FIELD = "exercise"   # ⚠ confirm
_STAT_ONE_RM_FIELD   = "ONE_RM"     # from design doc — confirm capitalization
_STAT_DATE_FIELD     = "date"       # ⚠ confirm
_STATS_LIST_KEY      = "stats"      # ⚠ key inside response JSON that holds the list
_NEXT_TOKEN_KEY      = "next_token" # pagination field

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
    """Insert rows, replacing on (name_normalized, exercise, test_date) conflict.
    When the input list itself contains duplicates, last occurrence wins.
    """
    if not rows:
        return
    # Deduplicate input: last occurrence of each (name, exercise, date) wins
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (row["name_normalized"], row["exercise"], row["test_date"])
        seen[key] = row
    deduped = list(seen.values())

    for row in deduped:
        conn.execute("""
            DELETE FROM perch_1rm
            WHERE name_normalized = ? AND exercise = ? AND test_date = ?
        """, [row["name_normalized"], row["exercise"], row["test_date"]])
    conn.executemany("""
        INSERT INTO perch_1rm (name_normalized, perch_user_id, exercise, one_rm_lbs, test_date)
        VALUES (?, ?, ?, ?, ?)
    """, [
        [r["name_normalized"], r["perch_user_id"], r["exercise"], r["one_rm_lbs"], r["test_date"]]
        for r in deduped
    ])
