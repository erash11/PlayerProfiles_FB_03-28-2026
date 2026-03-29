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
}


def _safe(val):
    """Convert NaN/inf to None for JSON serialization."""
    if val is None:
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


def render(
    df_scored: pd.DataFrame,
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
        "jump_height_t", "peak_power_bm_t", "mrsi_t",
        "hsd_t", "player_load_t", "max_vel_t", "weight_t",
        "jump_height_z", "peak_power_bm_z", "mrsi_z",
        "hsd_z", "player_load_z", "max_vel_z", "weight_z",
        "cmj_domain", "gps_domain", "bw_domain",
        "tsa_score", "tsa_rank", "rag", "missing_domains",
    ]
    # Only include columns that exist
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
            elif hasattr(v, "item"):          # numpy scalar
                rec[c] = _safe(v.item())
            else:
                rec[c] = v
        records.append(rec)

    # Team averages for display in metrics table
    numeric_cols = [
        "jump_height_cm", "peak_power_bm", "mrsi",
        "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms", "weight_kg",
    ]
    team_avg = {c: _safe(df[c].mean()) if c in df.columns else None for c in numeric_cols}

    # Coverage counts
    cmj_count = int(df["jump_height_cm"].notna().sum()) if "jump_height_cm" in df.columns else 0
    gps_count = int(df["avg_hsd_m"].notna().sum())       if "avg_hsd_m" in df.columns else 0
    bw_count  = int(df["weight_kg"].notna().sum())        if "weight_kg" in df.columns else 0

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
        positions=positions,
    )
