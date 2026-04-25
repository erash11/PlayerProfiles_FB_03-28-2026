"""Data loading and merging from all three sources."""

import re
from pathlib import Path

import duckdb
import pandas as pd

from config import FORCEPLATE_DB, GPS_DB, BODYWEIGHT_CSV, ROSTER_CSV, PERCH_DB


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


def load_cmj_history(start_date: str, end_date: str) -> pd.DataFrame:
    """
    All CMJ tests per athlete within [start_date, end_date] (not just most recent).
    Returns: forcedecks_id, test_date, jump_height_cm, peak_power_bm, mrsi
    Sorted by forcedecks_id, test_date ASC.
    """
    conn = duckdb.connect(str(FORCEPLATE_DB), read_only=True)

    all_tests = conn.execute("""
        SELECT athlete_id, test_id, test_date
        FROM classified_athletes
        WHERE test_date BETWEEN ? AND ?
        ORDER BY athlete_id, test_date
    """, [start_date, end_date]).df()

    if all_tests.empty:
        conn.close()
        return pd.DataFrame(columns=["forcedecks_id", "test_date", "jump_height_cm", "peak_power_bm", "mrsi"])

    test_ids = all_tests["test_id"].tolist()
    placeholders = ", ".join(["?" for _ in test_ids])

    raw = conn.execute(f"""
        SELECT test_id, metric_name, metric_value
        FROM raw_tests
        WHERE test_id IN ({placeholders})
          AND metric_name IN ('Jump Height (Imp-Mom)', 'Peak Power / BM')
    """, test_ids).df()

    classified = conn.execute(f"""
        SELECT test_id, athlete_id, mrsi
        FROM classified_athletes
        WHERE test_id IN ({placeholders})
    """, test_ids).df()

    conn.close()

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

    result = classified.merge(raw_wide, on="test_id", how="left")
    result = result.rename(columns={"athlete_id": "forcedecks_id"})
    result = result.merge(all_tests[["test_id", "test_date"]], on="test_id", how="left")

    cols = ["forcedecks_id", "test_date", "jump_height_cm", "peak_power_bm", "mrsi"]
    for c in cols:
        if c not in result.columns:
            result[c] = float("nan")

    return result[cols].sort_values(["forcedecks_id", "test_date"]).reset_index(drop=True)


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


def load_gps_history(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Per-session GPS data for all athletes in [start_date, end_date].
    Column rename: high_speed_distance_m -> hsd_m, total_player_load -> player_load.
    Returns: catapult_id, session_date, hsd_m, player_load, max_velocity_ms
    Sorted by catapult_id, session_date ASC.
    """
    conn = duckdb.connect(str(GPS_DB), read_only=True)

    result = conn.execute("""
        SELECT
            athlete_id            AS catapult_id,
            session_date,
            high_speed_distance_m AS hsd_m,
            total_player_load     AS player_load,
            max_velocity_ms
        FROM athlete_sessions
        WHERE session_date BETWEEN ? AND ?
        ORDER BY athlete_id, session_date
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


def load_bw_history(end_date: str) -> pd.DataFrame:
    """
    All body weight entries per athlete on or before end_date (not just most recent).
    Returns: name_normalized, date, weight_kg
    Sorted by name_normalized, date ASC.
    """
    df = pd.read_csv(BODYWEIGHT_CSV)
    df.columns = [c.strip().upper() for c in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"], format="%m/%d/%Y", errors="coerce")
    df = df.dropna(subset=["DATE"])
    df = df[df["DATE"] <= pd.Timestamp(end_date)]

    if df.empty:
        return pd.DataFrame(columns=["name_normalized", "date", "weight_kg"])

    def flip_name(raw):
        raw = str(raw).strip().strip('"')
        if "," in raw:
            parts = raw.split(",", 1)
            return f"{parts[1].strip()} {parts[0].strip()}"
        return raw

    df["full_name"] = df["NAME"].apply(flip_name)
    df["name_normalized"] = df["full_name"].apply(_normalize_name)
    df["weight_kg"] = pd.to_numeric(df["WEIGHT"], errors="coerce") * 0.453592
    df = df.rename(columns={"DATE": "date"})
    df = df.dropna(subset=["weight_kg"])

    return df[["name_normalized", "date", "weight_kg"]].sort_values(
        ["name_normalized", "date"]
    ).reset_index(drop=True)


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


def load_imtp_history(start_date: str, end_date: str) -> pd.DataFrame:
    """
    All IMTP tests per athlete within [start_date, end_date].
    Returns: forcedecks_id, test_date, peak_force_n, peak_force_bm, rfd_100ms, rfd_200ms
    Sorted by forcedecks_id, test_date ASC.
    """
    conn = duckdb.connect(str(FORCEPLATE_DB), read_only=True)

    tables = conn.execute("SHOW TABLES").df()
    if "imtp_tests" not in tables["name"].tolist():
        conn.close()
        return pd.DataFrame(columns=["forcedecks_id", "test_date", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    all_tests = conn.execute("""
        SELECT DISTINCT athlete_id, test_id, test_date
        FROM imtp_tests
        WHERE test_date BETWEEN ? AND ?
        ORDER BY athlete_id, test_date
    """, [start_date, end_date]).df()

    if all_tests.empty:
        conn.close()
        return pd.DataFrame(columns=["forcedecks_id", "test_date", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    test_ids = all_tests["test_id"].tolist()
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
        return pd.DataFrame(columns=["forcedecks_id", "test_date", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])

    raw_wide = raw.pivot_table(
        index="test_id", columns="metric_name", values="metric_value"
    ).reset_index()
    raw_wide.columns.name = None
    raw_wide = raw_wide.rename(columns={
        "Peak Vertical Force":      "peak_force_n",
        "Peak Vertical Force / BM": "peak_force_bm",
        "RFD - 100ms":              "rfd_100ms",
        "RFD - 200ms":              "rfd_200ms",
    })

    result = all_tests.merge(raw_wide, on="test_id", how="left")
    result = result.rename(columns={"athlete_id": "forcedecks_id"})

    cols = ["forcedecks_id", "test_date", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"]
    for c in cols:
        if c not in result.columns:
            result[c] = float("nan")

    return result[cols].sort_values(["forcedecks_id", "test_date"]).reset_index(drop=True)


def _load_bw_lbs(end_date: str) -> pd.DataFrame:
    """
    Most recent body weight per athlete on or before end_date, in lbs.
    Returns: name_normalized, weight_lbs
    """
    df = load_bodyweight(end_date)
    df["weight_lbs"] = df["weight_kg"] / 0.453592
    return df[["name_normalized", "weight_lbs"]]


def _load_fd_bw(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Most recent ForceDecks body weight per athlete within [start_date, end_date].
    Returns: forcedecks_id, weight_kg (kg — native FD unit).
    Returns empty DataFrame if DB is unreachable or has no matching rows.
    """
    try:
        conn = duckdb.connect(str(FORCEPLATE_DB), read_only=True)
        try:
            result = conn.execute("""
                SELECT athlete_id AS forcedecks_id, metric_value AS weight_kg
                FROM (
                    SELECT athlete_id, metric_value,
                           ROW_NUMBER() OVER (PARTITION BY athlete_id ORDER BY test_date DESC) AS rn
                    FROM raw_tests
                    WHERE metric_name = 'Bodyweight in Kilograms'
                      AND test_date <= ?
                ) t
                WHERE rn = 1
            """, [end_date]).df()
        finally:
            conn.close()
        return result
    except Exception:
        return pd.DataFrame(columns=["forcedecks_id", "weight_kg"])


def _load_bw_combined(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Body weight per athlete: CSV primary, ForceDecks raw_tests fallback.
    Returns: name_normalized, weight_kg
    CSV value wins; FD fills gaps for roster athletes missing from CSV.
    """
    csv_bw = load_bodyweight(end_date)  # name_normalized, weight_kg

    fd_bw = _load_fd_bw(start_date, end_date)
    if fd_bw.empty:
        return csv_bw.dropna(subset=["weight_kg"]).reset_index(drop=True)

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


def load_perch(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Most recent 1RM per exercise per athlete within [start_date, end_date],
    normalized by snapshot body weight (end_date).
    Returns: forcedecks_id, bs_1rm_bw, pc_1rm_bw, bp_1rm_bw, hpc_1rm_bw
    Returns empty DataFrame if perch.duckdb doesn't exist or has no data.
    """
    empty = pd.DataFrame(columns=["forcedecks_id", "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"])

    if not Path(PERCH_DB).exists():
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
        pivoted[f"{short}_1rm_lbs"] = pivoted[ex] if ex in pivoted.columns else float("nan")

    pivoted = pivoted[["name_normalized", "bs_1rm_lbs", "pc_1rm_lbs", "bp_1rm_lbs", "hpc_1rm_lbs"]]

    # Join roster to get forcedecks_id
    roster = pd.read_csv(ROSTER_CSV)
    roster["name_normalized"] = roster["full_name"].apply(_normalize_name)
    pivoted = pivoted.merge(roster[["name_normalized", "forcedecks_id"]], on="name_normalized", how="inner")

    # Normalize by snapshot body weight
    bw = _load_bw_lbs(end_date)
    pivoted = pivoted.merge(bw, on="name_normalized", how="left")

    fd_bw = _load_fd_bw(start_date, end_date)
    if not fd_bw.empty:
        fd_bw_lbs = fd_bw.assign(weight_lbs_fd=fd_bw["weight_kg"] / 0.453592)[["forcedecks_id", "weight_lbs_fd"]]
        pivoted = pivoted.merge(fd_bw_lbs, on="forcedecks_id", how="left")
        pivoted["weight_lbs"] = pivoted["weight_lbs"].combine_first(pivoted["weight_lbs_fd"])
        pivoted = pivoted.drop(columns=["weight_lbs_fd"])

    for ex in ["bs", "pc", "bp", "hpc"]:
        pivoted[f"{ex}_1rm_bw"] = pivoted[f"{ex}_1rm_lbs"] / pivoted["weight_lbs"]

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

    if not Path(PERCH_DB).exists():
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
        pivoted[f"{short}_1rm_lbs"] = pivoted[ex] if ex in pivoted.columns else float("nan")

    # Join roster
    roster = pd.read_csv(ROSTER_CSV)
    roster["name_normalized"] = roster["full_name"].apply(_normalize_name)
    pivoted = pivoted.merge(roster[["name_normalized", "forcedecks_id"]], on="name_normalized", how="inner")

    # Normalize by snapshot BW
    bw = _load_bw_lbs(end_date)
    pivoted = pivoted.merge(bw, on="name_normalized", how="left")

    fd_bw = _load_fd_bw(start_date, end_date)
    if not fd_bw.empty:
        fd_bw_lbs = fd_bw.assign(weight_lbs_fd=fd_bw["weight_kg"] / 0.453592)[["forcedecks_id", "weight_lbs_fd"]]
        pivoted = pivoted.merge(fd_bw_lbs, on="forcedecks_id", how="left")
        pivoted["weight_lbs"] = pivoted["weight_lbs"].combine_first(pivoted["weight_lbs_fd"])
        pivoted = pivoted.drop(columns=["weight_lbs_fd"])

    for ex in ["bs", "pc", "bp", "hpc"]:
        pivoted[f"{ex}_1rm_bw"] = pivoted[f"{ex}_1rm_lbs"] / pivoted["weight_lbs"]

    cols = ["forcedecks_id", "test_date", "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"]
    for c in cols:
        if c not in pivoted.columns:
            pivoted[c] = float("nan")

    return pivoted[cols].sort_values(["forcedecks_id", "test_date"]).reset_index(drop=True)


def merge_all(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Joins CMJ, GPS, body weight, IMTP, and Perch 1RM onto the athlete roster crosswalk.
    Athletes missing any domain get NaN for that domain's metrics.
    """
    roster = pd.read_csv(ROSTER_CSV)
    roster["name_normalized"] = roster["full_name"].apply(_normalize_name)

    cmj   = load_cmj(start_date, end_date)
    gps   = load_gps(start_date, end_date)
    bw    = _load_bw_combined(start_date, end_date)
    imtp  = load_imtp(start_date, end_date)
    perch = load_perch(start_date, end_date)

    df = roster.merge(cmj,   on="forcedecks_id",  how="left")
    df = df.merge(gps,   on="catapult_id",    how="left")
    df = df.merge(bw,    on="name_normalized", how="left")
    df = df.merge(imtp,  on="forcedecks_id",  how="left")
    df = df.merge(perch, on="forcedecks_id",  how="left")

    return df
