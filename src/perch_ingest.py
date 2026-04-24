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


# ── HTTP client ──────────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def fetch_users(token: str) -> dict[str, str]:
    """
    GET /v2/users (paginated).
    Returns {perch_user_id: name_normalized} for all users in the account.
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
    Returns raw stat records from the API.
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
        import json
        print("=== /v2/users (first page) ===")
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
