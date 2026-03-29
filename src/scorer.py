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
}

_CMJ_T  = ["jump_height_t", "peak_power_bm_t", "mrsi_t"]
_GPS_T  = ["hsd_t", "player_load_t", "max_vel_t"]
_BW_T   = ["weight_t"]


def _z_to_t(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.std() == 0 or len(valid) < 2:
        return pd.Series(50.0, index=series.index)
    z = (series - valid.mean()) / valid.std()
    return (z * 10 + 50).clip(0, 100)


def score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds t-score columns, domain scores, TSA composite, TSA rank, and RAG to df.
    Operates on available data only — athletes missing a domain get NaN for that domain.
    Returns a copy sorted by tsa_rank ascending.
    """
    out = df.copy()

    # T-scores for each metric (population = all athletes with that metric)
    for raw_col, t_col in _METRICS.items():
        out[t_col] = _z_to_t(out[raw_col])

    # Domain composites — mean of available t-scores in that domain
    out["cmj_domain"] = out[_CMJ_T].mean(axis=1, skipna=False)
    out["gps_domain"] = out[_GPS_T].mean(axis=1, skipna=False)
    out["bw_domain"]  = out[_BW_T].mean(axis=1, skipna=False)

    # TSA = mean of available domains (at least 1 required)
    domain_cols = ["cmj_domain", "gps_domain", "bw_domain"]
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
        if pd.isna(row["cmj_domain"]): domains.append("CMJ")
        if pd.isna(row["gps_domain"]): domains.append("GPS")
        if pd.isna(row["bw_domain"]):  domains.append("BW")
        missing.append(", ".join(domains))
    out["missing_domains"] = missing

    return out.sort_values("tsa_rank").reset_index(drop=True)
