"""Perch API ingest -> data/perch.duckdb local cache.

Run this before generating the report:
    python src/perch_ingest.py --start 2025-09-01 --end 2026-03-28

Uses /v3/sets (not /stats): 1RM = weight / pct_1rm per set where pct_1rm is set.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PERCH_DB

load_dotenv()

# ── Perch API constants (all confirmed via --probe) ──────────────────────────

PERCH_API_BASE = "https://api.perch.fit"

# /v2/users (POST)
_USER_ID_FIELD         = "id"
_USER_FIRST_NAME_FIELD = "first_name"
_USER_LAST_NAME_FIELD  = "last_name"
_USERS_LIST_KEY        = "data"
_NEXT_TOKEN_KEY        = "next_token"

# /v3/sets (POST)
_SET_USER_ID_FIELD = "user_id"    # int
_SET_WEIGHT_FIELD  = "weight"     # float, lbs
_SET_PCT_1RM_FIELD = "pct_1rm"    # float 0–1, or null
_SET_CREATED_AT    = "created_at" # Unix timestamp float
_SETS_LIST_KEY     = "data"

# exercise_id -> DB exercise name (confirmed from GET /v3/exercises)
_EXERCISE_ID_MAP: dict[int, str] = {
    1:  "Back Squat",
    2:  "Bench Press",
    19: "Power Clean",
    48: "Hang Power Clean",
}

# ────────────────────────────────────────────────────────────────────────────


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.strip().lower())


def _to_ts(date_str: str) -> float:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def _ts_to_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


# ── DB helpers ───────────────────────────────────────────────────────────────

def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
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
    if not rows:
        return
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (row["name_normalized"], row["exercise"], row["test_date"])
        if key not in seen or row["one_rm_lbs"] > seen[key]["one_rm_lbs"]:
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


def fetch_users(token: str) -> tuple[dict[int, str], int]:
    """
    POST /v2/users (paginated).
    Returns ({user_id: name_normalized}, group_id).
    """
    me = requests.get(f"{PERCH_API_BASE}/v2/user", headers=_headers(token), timeout=30)
    me.raise_for_status()
    group_id: int = me.json()["data"]["org_id"]

    url = f"{PERCH_API_BASE}/v2/users"
    id_to_name: dict[int, str] = {}
    payload: dict = {"group_id": group_id}

    while True:
        resp = requests.post(url, headers=_headers(token), json=payload, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        for u in body.get(_USERS_LIST_KEY, []):
            uid = u.get(_USER_ID_FIELD)
            if uid:
                first = u.get(_USER_FIRST_NAME_FIELD, "")
                last  = u.get(_USER_LAST_NAME_FIELD, "")
                id_to_name[uid] = _normalize_name(f"{first} {last}")

        next_tok = body.get(_NEXT_TOKEN_KEY)
        if not next_tok:
            break
        payload = {"group_id": group_id, _NEXT_TOKEN_KEY: next_tok}

    return id_to_name, group_id


def fetch_sets_1rm(token: str, start_date: str, end_date: str, group_id: int) -> list[dict]:
    """
    POST /v3/sets per target exercise.
    Pages newest-first; stops when created_at falls before start_date.
    Returns {user_id, exercise, one_rm_lbs, test_date} for each set with pct_1rm set.
    """
    start_ts = _to_ts(start_date)
    end_ts   = _to_ts(end_date) + 86400  # inclusive end (end of day UTC)

    rows: list[dict] = []

    for ex_id, ex_name in _EXERCISE_ID_MAP.items():
        payload: dict = {"group_id": group_id, "exercise_id": ex_id}
        page = 0

        while True:
            resp = requests.post(
                f"{PERCH_API_BASE}/v3/sets",
                headers=_headers(token), json=payload, timeout=30,
            )
            resp.raise_for_status()
            body  = resp.json()
            page += 1
            records = body.get(_SETS_LIST_KEY, [])

            past_start = False
            for s in records:
                created_at = s.get(_SET_CREATED_AT) or 0
                if created_at < start_ts:
                    past_start = True
                    break
                if created_at > end_ts:
                    continue
                pct = s.get(_SET_PCT_1RM_FIELD)
                wt  = s.get(_SET_WEIGHT_FIELD)
                if not pct or not wt:
                    continue
                rows.append({
                    "user_id":   s[_SET_USER_ID_FIELD],
                    "exercise":  ex_name,
                    "one_rm_lbs": wt / pct,
                    "test_date":  _ts_to_date(created_at),
                })

            next_tok = body.get(_NEXT_TOKEN_KEY)
            if not next_tok or past_start:
                break
            payload = {"group_id": group_id, "exercise_id": ex_id, _NEXT_TOKEN_KEY: next_tok}

        print(f"  {ex_name}: {page} page(s) fetched")

    return rows


# ── Main ingest ───────────────────────────────────────────────────────────────

def ingest(start_date: str, end_date: str, token: str, db_path=None) -> int:
    if db_path is None:
        db_path = PERCH_DB

    print("Fetching Perch users ...")
    id_to_name, group_id = fetch_users(token)
    print(f"  {len(id_to_name)} athletes found (group_id={group_id})")

    print(f"Fetching 1RM sets ({start_date} to {end_date}) ...")
    set_rows = fetch_sets_1rm(token, start_date, end_date, group_id)
    print(f"  {len(set_rows)} set records with pct_1rm in range")

    db_rows = []
    unmatched_users: set[int] = set()
    for row in set_rows:
        name_norm = id_to_name.get(row["user_id"])
        if not name_norm:
            unmatched_users.add(row["user_id"])
            continue
        db_rows.append({
            "name_normalized": name_norm,
            "perch_user_id":   str(row["user_id"]),
            "exercise":        row["exercise"],
            "one_rm_lbs":      float(row["one_rm_lbs"]),
            "test_date":       row["test_date"],
        })

    if unmatched_users:
        print(f"  Skipped {len(unmatched_users)} user IDs not in users list: {sorted(unmatched_users)[:10]}")

    conn = duckdb.connect(str(db_path))
    ensure_schema(conn)
    upsert_rows(conn, db_rows)
    conn.close()

    print(f"  Upserted {len(db_rows)} rows to {db_path}")
    return len(db_rows)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest Perch 1RM data into local DuckDB cache")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD (required unless --probe)")
    parser.add_argument("--end",   default=None, help="End date YYYY-MM-DD (required unless --probe)")
    parser.add_argument("--probe", action="store_true",
                        help="Dump raw API responses to verify connectivity, then exit")
    args = parser.parse_args()

    if not args.probe and (not args.start or not args.end):
        parser.error("--start and --end are required unless --probe is used")

    token = os.environ.get("PERCH_API_TOKEN")
    if not token:
        sys.exit("ERROR: PERCH_API_TOKEN not set. Add it to .env or export it.")

    if args.probe:
        import json
        from datetime import date, timedelta

        def _dump(label, r):
            print(f"=== {label} ===")
            print(f"  Status: {r.status_code}  URL: {r.url}")
            try:
                print(json.dumps(r.json(), indent=2)[:2000])
            except Exception:
                print(f"  (non-JSON): {r.text[:500]}")

        me = requests.get(f"{PERCH_API_BASE}/v2/user", headers=_headers(token), timeout=30)
        group_id = me.json()["data"]["org_id"]

        resp_users = requests.post(f"{PERCH_API_BASE}/v2/users", headers=_headers(token),
                                   json={"group_id": group_id}, timeout=30)
        _dump(f"/v2/users POST group_id={group_id} (first page)", resp_users)

        resp_sets = requests.post(f"{PERCH_API_BASE}/v3/sets", headers=_headers(token),
                                  json={"group_id": group_id, "exercise_id": 1}, timeout=30)
        _dump("/v3/sets POST exercise_id=1 Back Squat (first page)", resp_sets)
        body = resp_sets.json()
        with_pct = [s for s in body.get("data", []) if s.get("pct_1rm")]
        if with_pct:
            s = with_pct[0]
            print(f"\nSample 1RM calc: weight={s['weight']} / pct_1rm={s['pct_1rm']:.4f}"
                  f" = {s['weight']/s['pct_1rm']:.1f} lbs  user_id={s['user_id']}"
                  f"  date={_ts_to_date(s['created_at'])}")

        print("\nProbe complete. API is reachable and returning data.")
        return

    ingest(args.start, args.end, token)


if __name__ == "__main__":
    main()
