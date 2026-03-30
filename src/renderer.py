"""Renders the scored DataFrame into a self-contained HTML string."""

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from config import PROJECT_ROOT

_TEMPLATE_DIR = PROJECT_ROOT / "templates"

# Raw metric columns and their matching z-score column names for the template
_Z_MAP = {
    "jump_height_cm":      "jump_height_z",
    "peak_power_bm":       "peak_power_bm_z",
    "mrsi":                "mrsi_z",
    "avg_hsd_m":           "hsd_z",
    "avg_player_load":     "player_load_z",
    "avg_max_velocity_ms": "max_vel_z",
    "weight_kg":           "weight_z",
    "peak_force_bm":       "peak_force_bm_z",
    "peak_force_n":        "peak_force_n_z",
    "rfd_100ms":           "rfd_100ms_z",
    "rfd_200ms":           "rfd_200ms_z",
}


def _safe(val):
    """Convert NaN/inf/NaT to None for JSON serialization."""
    if val is None:
        return None
    if val is pd.NaT:
        return None
    try:
        if math.isnan(val) or math.isinf(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _add_z_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add raw z-score columns (pre-t-score conversion) for display in metrics table."""
    out = df.copy()
    for raw_col, z_col in _Z_MAP.items():
        if raw_col in out.columns:
            valid = out[raw_col].dropna()
            if len(valid) >= 2 and valid.std() > 0:
                out[z_col] = (out[raw_col] - valid.mean()) / valid.std()
            else:
                out[z_col] = float("nan")
        else:
            out[z_col] = float("nan")
    return out


def _t_score_val(val, stats: dict):
    """T-score a single historical value using snapshot population stats."""
    if stats.get("mean") is None or stats.get("std") is None:
        return None
    if val is None:
        return None
    try:
        if math.isnan(float(val)):
            return None
    except (TypeError, ValueError):
        return None
    z = (float(val) - stats["mean"]) / stats["std"]
    return round(max(0.0, min(100.0, z * 10 + 50)), 1)


def _domain_t(vals: list):
    """Mean of non-None t-score values, or None if all are missing."""
    valid = [v for v in vals if v is not None]
    return round(sum(valid) / len(valid), 1) if valid else None


def _gps_rolling(df_athlete: pd.DataFrame) -> pd.DataFrame:
    """
    7-day rolling average for a single athlete's GPS sessions.
    Inserts a null sentinel row for any gap > 21 days so Chart.js renders a break.
    """
    df = df_athlete.copy()
    df["session_date"] = pd.to_datetime(df["session_date"])
    df = df.sort_values("session_date").set_index("session_date")

    metric_cols = ["hsd_m", "player_load", "max_velocity_ms"]
    rolled = df[metric_cols].rolling("7D", min_periods=1).mean().reset_index()

    result_rows = []
    prev_date = None
    for _, row in rolled.iterrows():
        if prev_date is not None and (row["session_date"] - prev_date).days > 21:
            null_row = {"session_date": prev_date + pd.Timedelta(days=(row["session_date"] - prev_date).days // 2)}
            for col in metric_cols:
                null_row[col] = None
            result_rows.append(null_row)
        result_rows.append(row.to_dict())
        prev_date = row["session_date"]

    return pd.DataFrame(result_rows)


def build_history(athlete_records, cmj_hist, gps_hist, bw_hist, imtp_hist, pop_stats):
    """
    Attaches *_history arrays to each athlete dict in athlete_records (in-place).
    pop_stats keys match snapshot raw column names (e.g. 'avg_hsd_m' for GPS).
    GPS history uses 7-day rolling average; null sentinel rows mark off-season gaps.
    """
    from src.data import _normalize_name

    def _grp(df, col):
        return df.groupby(col) if not df.empty and col in df.columns else {}

    cmj_grp  = _grp(cmj_hist,  "forcedecks_id")
    imtp_grp = _grp(imtp_hist, "forcedecks_id")
    bw_grp   = _grp(bw_hist,   "name_normalized")
    gps_grp  = _grp(gps_hist,  "catapult_id")

    for rec in athlete_records:
        fd_id     = rec.get("forcedecks_id")
        cat_id    = rec.get("catapult_id")
        name_norm = _normalize_name(rec.get("full_name", ""))

        # ── CMJ ──
        rec["cmj_history"] = []
        if fd_id and hasattr(cmj_grp, "groups") and fd_id in cmj_grp.groups:
            for _, row in cmj_grp.get_group(fd_id).iterrows():
                jh_t = _t_score_val(row.get("jump_height_cm"), pop_stats.get("jump_height_cm", {}))
                pp_t = _t_score_val(row.get("peak_power_bm"),  pop_stats.get("peak_power_bm", {}))
                mr_t = _t_score_val(row.get("mrsi"),           pop_stats.get("mrsi", {}))
                rec["cmj_history"].append({
                    "date":            str(row["test_date"])[:10],
                    "jump_height_cm":  _safe(row.get("jump_height_cm")),
                    "peak_power_bm":   _safe(row.get("peak_power_bm")),
                    "mrsi":            _safe(row.get("mrsi")),
                    "jump_height_t":   jh_t,
                    "peak_power_bm_t": pp_t,
                    "mrsi_t":          mr_t,
                    "cmj_domain_t":    _domain_t([jh_t, pp_t, mr_t]),
                })

        # ── IMTP ──
        rec["imtp_history"] = []
        if fd_id and hasattr(imtp_grp, "groups") and fd_id in imtp_grp.groups:
            for _, row in imtp_grp.get_group(fd_id).iterrows():
                pf_t  = _t_score_val(row.get("peak_force_bm"), pop_stats.get("peak_force_bm", {}))
                r1_t  = _t_score_val(row.get("rfd_100ms"),     pop_stats.get("rfd_100ms", {}))
                r2_t  = _t_score_val(row.get("rfd_200ms"),     pop_stats.get("rfd_200ms", {}))
                rec["imtp_history"].append({
                    "date":             str(row["test_date"])[:10],
                    "peak_force_n":     _safe(row.get("peak_force_n")),
                    "peak_force_bm":    _safe(row.get("peak_force_bm")),
                    "rfd_100ms":        _safe(row.get("rfd_100ms")),
                    "rfd_200ms":        _safe(row.get("rfd_200ms")),
                    "peak_force_bm_t":  pf_t,
                    "rfd_100ms_t":      r1_t,
                    "rfd_200ms_t":      r2_t,
                    "str_domain_t":     pf_t,   # Strength domain = peak_force_bm_t only
                })

        # ── Body Weight ──
        rec["bw_history"] = []
        if name_norm and hasattr(bw_grp, "groups") and name_norm in bw_grp.groups:
            for _, row in bw_grp.get_group(name_norm).iterrows():
                wt_t = _t_score_val(row.get("weight_kg"), pop_stats.get("weight_kg", {}))
                rec["bw_history"].append({
                    "date":        str(row["date"])[:10],
                    "weight_kg":   _safe(row.get("weight_kg")),
                    "weight_t":    wt_t,
                    "bw_domain_t": wt_t,
                })

        # ── GPS ──
        rec["gps_history"] = []
        if cat_id and hasattr(gps_grp, "groups") and cat_id in gps_grp.groups:
            df_rolled = _gps_rolling(gps_grp.get_group(cat_id))
            for _, row in df_rolled.iterrows():
                hsd = row.get("hsd_m")
                pl  = row.get("player_load")
                mv  = row.get("max_velocity_ms")
                hsd_t = _t_score_val(hsd, pop_stats.get("avg_hsd_m", {}))           if hsd is not None else None
                pl_t  = _t_score_val(pl,  pop_stats.get("avg_player_load", {}))     if pl  is not None else None
                mv_t  = _t_score_val(mv,  pop_stats.get("avg_max_velocity_ms", {})) if mv  is not None else None
                rec["gps_history"].append({
                    "date":             str(row["session_date"])[:10],
                    "hsd_m":            _safe(hsd) if hsd is not None else None,
                    "player_load":      _safe(pl)  if pl  is not None else None,
                    "max_velocity_ms":  _safe(mv)  if mv  is not None else None,
                    "hsd_t":            hsd_t,
                    "player_load_t":    pl_t,
                    "max_vel_t":        mv_t,
                    "gps_domain_t":     _domain_t([hsd_t, pl_t, mv_t]),
                })


def render(
    df_scored: pd.DataFrame,
    pop_stats: dict,
    cmj_hist: pd.DataFrame,
    gps_hist: pd.DataFrame,
    bw_hist: pd.DataFrame,
    imtp_hist: pd.DataFrame,
    label: str,
    start_date: str,
    end_date: str,
) -> str:
    df = _add_z_columns(df_scored)

    # Columns to include in the JSON payload
    include_cols = [
        "full_name", "jersey_number", "position", "catapult_id", "forcedecks_id",
        "jump_height_cm", "peak_power_bm", "mrsi",
        "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms", "weight_kg",
        "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms",
        "jump_height_t", "peak_power_bm_t", "mrsi_t",
        "hsd_t", "player_load_t", "max_vel_t", "weight_t",
        "peak_force_bm_t", "peak_force_n_t", "rfd_100ms_t", "rfd_200ms_t",
        "jump_height_z", "peak_power_bm_z", "mrsi_z",
        "hsd_z", "player_load_z", "max_vel_z", "weight_z",
        "peak_force_bm_z", "peak_force_n_z", "rfd_100ms_z", "rfd_200ms_z",
        "cmj_domain", "gps_domain", "bw_domain", "strength_domain",
        "tsa_score", "tsa_rank", "rag", "missing_domains",
    ]
    cols = [c for c in include_cols if c in df.columns]

    records = []
    for _, row in df[cols].iterrows():
        rec = {}
        for c in cols:
            v = row[c]
            if pd.isna(v) if not isinstance(v, str) else False:
                rec[c] = None
            elif isinstance(v, (int, float)):
                rec[c] = _safe(float(v))
            elif hasattr(v, "item"):
                rec[c] = _safe(v.item())
            else:
                rec[c] = v
        records.append(rec)

    # Attach longitudinal history arrays to each athlete record
    build_history(records, cmj_hist, gps_hist, bw_hist, imtp_hist, pop_stats)

    # Team averages
    numeric_cols = [
        "jump_height_cm", "peak_power_bm", "mrsi",
        "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms", "weight_kg",
        "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms",
    ]
    team_avg = {c: _safe(df[c].mean()) if c in df.columns else None for c in numeric_cols}

    cmj_count  = int(df["jump_height_cm"].notna().sum()) if "jump_height_cm" in df.columns else 0
    gps_count  = int(df["avg_hsd_m"].notna().sum())      if "avg_hsd_m" in df.columns else 0
    bw_count   = int(df["weight_kg"].notna().sum())       if "weight_kg" in df.columns else 0
    imtp_count = int(df["peak_force_bm"].notna().sum())   if "peak_force_bm" in df.columns else 0

    positions = sorted(df["position"].dropna().unique().tolist())

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)
    tmpl = env.get_template("report.html.j2")

    return tmpl.render(
        label=label,
        start_date=start_date,
        end_date=end_date,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        athletes=records,
        athletes_json=json.dumps(records, ensure_ascii=False),
        team_avg=team_avg,
        cmj_count=cmj_count,
        gps_count=gps_count,
        bw_count=bw_count,
        imtp_count=imtp_count,
        positions=positions,
    )
