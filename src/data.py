"""Data loading and merging from all three sources."""

import re
import duckdb
import pandas as pd

from config import FORCEPLATE_DB, GPS_DB, BODYWEIGHT_CSV, ROSTER_CSV


def _normalize_name(name: str) -> str:
    """Lowercase, strip extra whitespace, remove punctuation for fuzzy join."""
    return re.sub(r"[^a-z ]", "", name.strip().lower())


def load_cmj(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Most recent CMJ test per athlete within [start_date, end_date].
    Returns: forcedecks_id, jump_height_cm, peak_power_bm, mrsi
    """
    conn = duckdb.connect(str(FORCEPLATE_DB), read_only=True)

    # Most recent test_id per athlete in period
    latest = conn.execute("""
        SELECT athlete_id, test_id
        FROM (
            SELECT athlete_id, test_id,
                   ROW_NUMBER() OVER (PARTITION BY athlete_id ORDER BY test_date DESC) AS rn
            FROM classified_athletes
            WHERE test_date BETWEEN ? AND ?
        ) t
        WHERE rn = 1
    """, [start_date, end_date]).df()

    if latest.empty:
        conn.close()
        return pd.DataFrame(columns=["forcedecks_id", "jump_height_cm", "peak_power_bm", "mrsi"])

    test_ids = latest["test_id"].tolist()
    placeholders = ", ".join(["?" for _ in test_ids])

    # Raw metrics pivot: jump height and peak power / BM
    raw = conn.execute(f"""
        SELECT test_id, metric_name, metric_value
        FROM raw_tests
        WHERE test_id IN ({placeholders})
          AND metric_name IN ('Jump Height (Imp-Mom)', 'Peak Power / BM')
    """, test_ids).df()

    # mRSI from classified
    classified = conn.execute(f"""
        SELECT test_id, athlete_id, mrsi
        FROM classified_athletes
        WHERE test_id IN ({placeholders})
    """, test_ids).df()

    conn.close()

    # Pivot raw metrics wide
    if not raw.empty:
        raw_wide = raw.pivot_table(
            index="test_id", columns="metric_name", values="metric_value"
        ).reset_index()
        raw_wide.columns.name = None
        raw_wide = raw_wide.rename(columns={
            "Jump Height (Imp-Mom)": "jump_height_cm",
            "Peak Power / BM":       "peak_power_bm",
        })
    else:
        raw_wide = pd.DataFrame(columns=["test_id", "jump_height_cm", "peak_power_bm"])

    # Merge classified + raw
    result = classified.merge(raw_wide, on="test_id", how="left")
    result = result.rename(columns={"athlete_id": "forcedecks_id"})

    cols = ["forcedecks_id", "jump_height_cm", "peak_power_bm", "mrsi"]
    for c in cols:
        if c not in result.columns:
            result[c] = float("nan")

    return result[cols]


def load_gps(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Average GPS metrics per athlete across all sessions in [start_date, end_date].
    Returns: catapult_id, avg_hsd_m, avg_player_load, avg_max_velocity_ms
    """
    conn = duckdb.connect(str(GPS_DB), read_only=True)

    result = conn.execute("""
        SELECT
            athlete_id                       AS catapult_id,
            AVG(high_speed_distance_m)       AS avg_hsd_m,
            AVG(total_player_load)           AS avg_player_load,
            AVG(max_velocity_ms)             AS avg_max_velocity_ms
        FROM athlete_sessions
        WHERE session_date BETWEEN ? AND ?
        GROUP BY athlete_id
    """, [start_date, end_date]).df()

    conn.close()
    return result


def load_bodyweight(end_date: str) -> pd.DataFrame:
    """
    Most recent body weight per athlete on or before end_date.
    Converts lbs → kg. Normalizes name to 'First Last' for joining.
    Returns: name_normalized, weight_kg
    """
    df = pd.read_csv(BODYWEIGHT_CSV)
    df.columns = [c.strip().upper() for c in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"], format="%m/%d/%Y", errors="coerce")
    df = df.dropna(subset=["DATE"])
    df = df[df["DATE"] <= pd.Timestamp(end_date)]

    if df.empty:
        return pd.DataFrame(columns=["name_normalized", "weight_kg"])

    # Convert "Last, First" → "First Last"
    def flip_name(raw):
        raw = str(raw).strip().strip('"')
        if "," in raw:
            parts = raw.split(",", 1)
            return f"{parts[1].strip()} {parts[0].strip()}"
        return raw

    df["full_name"] = df["NAME"].apply(flip_name)
    df["name_normalized"] = df["full_name"].apply(_normalize_name)
    df["weight_kg"] = pd.to_numeric(df["WEIGHT"], errors="coerce") * 0.453592

    # Keep most recent per athlete
    df = df.sort_values("DATE", ascending=False)
    df = df.drop_duplicates(subset="name_normalized", keep="first")

    return df[["name_normalized", "weight_kg"]]


def load_imtp(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Most recent IMTP test per athlete within [start_date, end_date].
    Returns: forcedecks_id, peak_force_n, peak_force_bm, rfd_100ms, rfd_200ms
    """
    conn = duckdb.connect(str(FORCEPLATE_DB), read_only=True)

    # Check table exists (may not exist if pipeline hasn't run yet)
    tables = conn.execute("SHOW TABLES").df()
    if "imtp_tests" not in tables["name"].tolist():
        conn.close()
        return pd.DataFrame(columns=["forcedecks_id", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    latest = conn.execute("""
        SELECT athlete_id, test_id
        FROM (
            SELECT athlete_id, test_id,
                   ROW_NUMBER() OVER (PARTITION BY athlete_id ORDER BY test_date DESC) AS rn
            FROM imtp_tests
            WHERE test_date BETWEEN ? AND ?
        ) t
        WHERE rn = 1
    """, [start_date, end_date]).df()

    if latest.empty:
        conn.close()
        return pd.DataFrame(columns=["forcedecks_id", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    test_ids = latest["test_id"].tolist()
    placeholders = ", ".join(["?" for _ in test_ids])

    raw = conn.execute(f"""
        SELECT test_id, metric_name, metric_value
        FROM imtp_tests
        WHERE test_id IN ({placeholders})
          AND metric_name IN (
              'Peak Vertical Force',
              'Peak Vertical Force / BM',
              'RFD - 100ms',
              'RFD - 200ms'
          )
    """, test_ids).df()

    conn.close()

    if raw.empty:
        return pd.DataFrame(columns=["forcedecks_id", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    raw_wide = raw.pivot_table(
        index="test_id", columns="metric_name", values="metric_value"
    ).reset_index()
    raw_wide.columns.name = None
    raw_wide = raw_wide.rename(columns={
        "Peak Vertical Force":       "peak_force_n",
        "Peak Vertical Force / BM":  "peak_force_bm",
        "RFD - 100ms":               "rfd_100ms",
        "RFD - 200ms":               "rfd_200ms",
    })

    result = latest.merge(raw_wide, on="test_id", how="left")
    result = result.rename(columns={"athlete_id": "forcedecks_id"})

    cols = ["forcedecks_id", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"]
    for c in cols:
        if c not in result.columns:
            result[c] = float("nan")

    return result[cols]


def merge_all(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Joins CMJ, GPS, and body weight onto the athlete roster crosswalk.
    Athletes missing a domain get NaN for that domain's metrics.
    """
    roster = pd.read_csv(ROSTER_CSV)
    roster["name_normalized"] = roster["full_name"].apply(_normalize_name)

    cmj  = load_cmj(start_date, end_date)
    gps  = load_gps(start_date, end_date)
    bw   = load_bodyweight(end_date)
    imtp = load_imtp(start_date, end_date)

    df = roster.merge(cmj,  on="forcedecks_id", how="left")
    df = df.merge(gps,  on="catapult_id",   how="left")
    df = df.merge(bw,   on="name_normalized", how="left")
    df = df.merge(imtp, on="forcedecks_id", how="left")

    return df
