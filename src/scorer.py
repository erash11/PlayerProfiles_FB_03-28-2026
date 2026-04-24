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
    # IMTP — peak_force_bm drives the Strength domain; rfd metrics are display-only
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

_CMJ_T         = ["jump_height_t", "peak_power_bm_t", "mrsi_t"]
_GPS_T         = ["hsd_t", "player_load_t", "max_vel_t"]
_BW_T          = ["weight_t"]
_STRENGTH_T    = ["peak_force_bm_t"]
_WEIGHT_ROOM_T = ["bs_1rm_bw_t", "pc_1rm_bw_t", "bp_1rm_bw_t", "hpc_1rm_bw_t"]


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

    # T-scores for each metric; collect population stats for history scoring
    for raw_col, t_col in _METRICS.items():
        series = out[raw_col] if raw_col in out.columns else pd.Series(dtype=float, index=out.index)
        valid = series.dropna()
        if len(valid) >= 2 and valid.std() > 0:
            pop_stats[raw_col] = {"mean": float(valid.mean()), "std": float(valid.std())}
        else:
            pop_stats[raw_col] = {"mean": None, "std": None}
        out[t_col] = _z_to_t(series) if raw_col in out.columns else pd.Series(50.0, index=out.index)

    # Domain composites — mean of available t-scores in that domain
    out["cmj_domain"]      = out[_CMJ_T].mean(axis=1, skipna=False)
    out["gps_domain"]      = out[_GPS_T].mean(axis=1, skipna=False)
    out["bw_domain"]       = out[_BW_T].mean(axis=1, skipna=False)
    out["strength_domain"] = out[_STRENGTH_T].mean(axis=1, skipna=False)

    # Weight Room: partial exercise data still contributes; NaN only when all 4 are missing
    wr_t_present = out[_WEIGHT_ROOM_T].notna().any(axis=1)
    out["weight_room_domain"] = out[_WEIGHT_ROOM_T].mean(axis=1, skipna=True).where(wr_t_present)

    # TSA = mean of available domains (at least 1 required)
    domain_cols = ["cmj_domain", "gps_domain", "bw_domain", "strength_domain", "weight_room_domain"]
    out["tsa_score"] = out[domain_cols].mean(axis=1, skipna=True)

    # Rank (1 = highest TSA)
    out["tsa_rank"] = out["tsa_score"].rank(ascending=False, method="min").astype("Int64")

    # RAG — roster-relative tertiles
    green_thresh = out["tsa_score"].quantile(2 / 3)
    amber_thresh = out["tsa_score"].quantile(1 / 3)
    out["rag"] = np.select(
        [out["tsa_score"] >= green_thresh, out["tsa_score"] >= amber_thresh],
        ["green", "amber"],
        default="red",
    )

    # Flag athletes missing one or more domains
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
