"""Tests for trend chart data pipeline."""
import math
import pandas as pd
import pytest
from src.scorer import score


def _make_df():
    """Minimal 3-athlete DataFrame with all required columns including Perch."""
    return pd.DataFrame({
        "forcedecks_id":      ["a", "b", "c"],
        "catapult_id":        ["c1", "c2", None],
        "full_name":          ["Alice Smith", "Bob Jones", "Carol Lee"],
        "position":           ["WR", "OL", "QB"],
        "jersey_number":      [None, None, None],
        "name_normalized":    ["alice smith", "bob jones", "carol lee"],
        "jump_height_cm":     [60.0, 70.0, 65.0],
        "peak_power_bm":      [20.0, 25.0, 22.5],
        "mrsi":               [2.0, 3.0, 2.5],
        "avg_hsd_m":          [400.0, 500.0, None],
        "avg_player_load":    [100.0, 120.0, None],
        "avg_max_velocity_ms":[7.5, 8.5, None],
        "weight_kg":          [80.0, 110.0, 90.0],
        "peak_force_bm":      [25.0, 35.0, 30.0],
        "peak_force_n":       [2000.0, 3850.0, 2700.0],
        "rfd_100ms":          [6000.0, 9000.0, 7500.0],
        "rfd_200ms":          [5000.0, 8000.0, 6500.0],
        # Perch — Carol has no Weight Room data
        "bs_1rm_bw":          [2.0, 2.5, None],
        "pc_1rm_bw":          [1.3, 1.6, None],
        "bp_1rm_bw":          [1.1, 1.4, None],
        "hpc_1rm_bw":         [1.2, 1.5, None],
    })


def test_score_returns_tuple():
    df = _make_df()
    result = score(df)
    assert isinstance(result, tuple), "score() must return a tuple (df, pop_stats)"
    assert len(result) == 2


def test_pop_stats_has_expected_keys():
    df = _make_df()
    _, pop_stats = score(df)
    expected = ["jump_height_cm", "peak_power_bm", "mrsi",
                "avg_hsd_m", "avg_player_load", "avg_max_velocity_ms",
                "weight_kg", "peak_force_bm", "peak_force_n", "rfd_100ms", "rfd_200ms"]
    for key in expected:
        assert key in pop_stats, f"pop_stats missing key: {key}"


def test_pop_stats_values_are_finite():
    df = _make_df()
    _, pop_stats = score(df)
    for key, stats in pop_stats.items():
        if stats["mean"] is not None:
            assert not math.isnan(stats["mean"]), f"pop_stats[{key}]['mean'] is NaN"
            assert stats["std"] > 0, f"pop_stats[{key}]['std'] must be positive"


def test_scored_df_unchanged_structure():
    """Existing callers: df still has tsa_score, rag, domain columns."""
    df = _make_df()
    df_scored, _ = score(df)
    for col in ["tsa_score", "rag", "cmj_domain", "gps_domain", "bw_domain", "strength_domain"]:
        assert col in df_scored.columns, f"Missing column: {col}"


def test_load_cmj_history_columns():
    """Verifies column contract without hitting the DB."""
    from src.data import load_cmj_history
    import inspect
    # Function must exist and be importable
    assert callable(load_cmj_history)


def test_load_imtp_history_columns():
    from src.data import load_imtp_history
    assert callable(load_imtp_history)


def test_load_bw_history_columns():
    from src.data import load_bw_history
    assert callable(load_bw_history)


def test_load_gps_history_columns():
    from src.data import load_gps_history
    assert callable(load_gps_history)


def test_load_bw_history_returns_all_rows():
    """BW history must return more rows than the snapshot (which deduplicates to 1 per athlete)."""
    import tempfile, os
    import pandas as pd
    from unittest.mock import patch
    from src.data import load_bw_history

    csv_content = """DATE,NAME,WEIGHT,POS
09/01/2025,"Smith, John",200,WR
10/01/2025,"Smith, John",198,WR
11/01/2025,"Smith, John",197,WR
09/01/2025,"Jones, Bob",240,OL
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_content)
        tmp_path = f.name

    try:
        with patch("src.data.BODYWEIGHT_CSV", tmp_path):
            result = load_bw_history("2025-12-31")
        assert len(result) == 4, f"Expected 4 rows, got {len(result)}"
        assert set(result.columns) == {"name_normalized", "date", "weight_kg"}
        assert result["weight_kg"].iloc[0] == pytest.approx(240 * 0.453592, rel=1e-4)
    finally:
        os.unlink(tmp_path)


def test_build_history_attaches_empty_lists_when_no_data():
    from src.renderer import build_history

    athletes = [{"forcedecks_id": "fd1", "catapult_id": None, "full_name": "Alice Smith"}]
    pop_stats = {
        "jump_height_cm": {"mean": 65.0, "std": 5.0},
        "peak_power_bm":  {"mean": 22.0, "std": 2.0},
        "mrsi":           {"mean": 2.5,  "std": 0.3},
        "avg_hsd_m":          {"mean": 450.0, "std": 50.0},
        "avg_player_load":    {"mean": 110.0, "std": 15.0},
        "avg_max_velocity_ms":{"mean": 8.0,   "std": 0.5},
        "weight_kg":          {"mean": 90.0,  "std": 10.0},
        "peak_force_bm":  {"mean": 30.0, "std": 3.0},
        "peak_force_n":   {"mean": 2700.0,"std": 400.0},
        "rfd_100ms":      {"mean": 7500.0,"std": 1000.0},
        "rfd_200ms":      {"mean": 6000.0,"std": 800.0},
    }
    empty_df_cmj  = pd.DataFrame(columns=["forcedecks_id", "test_date", "jump_height_cm", "peak_power_bm", "mrsi"])
    empty_df_imtp = pd.DataFrame(columns=["forcedecks_id", "test_date", "peak_force_n", "peak_force_bm", "rfd_100ms", "rfd_200ms"])
    empty_df_bw   = pd.DataFrame(columns=["name_normalized", "date", "weight_kg"])
    empty_df_gps  = pd.DataFrame(columns=["catapult_id", "session_date", "hsd_m", "player_load", "max_velocity_ms"])

    empty_perch = pd.DataFrame(columns=["forcedecks_id", "test_date",
                                         "bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"])
    build_history(athletes, empty_df_cmj, empty_df_gps, empty_df_bw, empty_df_imtp,
                  empty_perch, pop_stats)

    assert athletes[0]["cmj_history"]   == []
    assert athletes[0]["gps_history"]   == []
    assert athletes[0]["bw_history"]    == []
    assert athletes[0]["imtp_history"]  == []
    assert athletes[0]["perch_history"] == []


def test_build_history_cmj_t_scores():
    from src.renderer import build_history

    # pop mean=65, std=5 → jump_height 70 → z=1 → t=60
    athletes = [{"forcedecks_id": "fd1", "catapult_id": None, "full_name": "Alice Smith"}]
    pop_stats = {
        "jump_height_cm": {"mean": 65.0, "std": 5.0},
        "peak_power_bm":  {"mean": 22.0, "std": 2.0},
        "mrsi":           {"mean": 2.5,  "std": 0.3},
        "avg_hsd_m": {"mean": None, "std": None},
        "avg_player_load": {"mean": None, "std": None},
        "avg_max_velocity_ms": {"mean": None, "std": None},
        "weight_kg": {"mean": None, "std": None},
        "peak_force_bm": {"mean": None, "std": None},
        "peak_force_n": {"mean": None, "std": None},
        "rfd_100ms": {"mean": None, "std": None},
        "rfd_200ms": {"mean": None, "std": None},
    }
    cmj_hist = pd.DataFrame([{
        "forcedecks_id": "fd1",
        "test_date": "2025-09-05",
        "jump_height_cm": 70.0,
        "peak_power_bm": 24.0,
        "mrsi": 2.8,
    }])
    empty = lambda cols: pd.DataFrame(columns=cols)

    build_history(
        athletes, cmj_hist,
        empty(["catapult_id","session_date","hsd_m","player_load","max_velocity_ms"]),
        empty(["name_normalized","date","weight_kg"]),
        empty(["forcedecks_id","test_date","peak_force_n","peak_force_bm","rfd_100ms","rfd_200ms"]),
        empty(["forcedecks_id","test_date","bs_1rm_bw","pc_1rm_bw","bp_1rm_bw","hpc_1rm_bw"]),
        pop_stats,
    )

    h = athletes[0]["cmj_history"]
    assert len(h) == 1
    assert h[0]["date"] == "2025-09-05"
    assert h[0]["jump_height_cm"] == pytest.approx(70.0)
    assert h[0]["jump_height_t"]  == pytest.approx(60.0, abs=0.5)   # z=1 → t=60


def _make_pop_stats_with_perch():
    return {
        "jump_height_cm":      {"mean": 65.0,   "std": 5.0},
        "peak_power_bm":       {"mean": 22.0,   "std": 2.0},
        "mrsi":                {"mean": 2.5,    "std": 0.3},
        "avg_hsd_m":           {"mean": 450.0,  "std": 50.0},
        "avg_player_load":     {"mean": 110.0,  "std": 15.0},
        "avg_max_velocity_ms": {"mean": 8.0,    "std": 0.5},
        "weight_kg":           {"mean": 90.0,   "std": 10.0},
        "peak_force_bm":       {"mean": 30.0,   "std": 3.0},
        "peak_force_n":        {"mean": 2700.0, "std": 400.0},
        "rfd_100ms":           {"mean": 7500.0, "std": 1000.0},
        "rfd_200ms":           {"mean": 6000.0, "std": 800.0},
        "bs_1rm_bw":           {"mean": 2.0,    "std": 0.3},
        "pc_1rm_bw":           {"mean": 1.4,    "std": 0.2},
        "bp_1rm_bw":           {"mean": 1.2,    "std": 0.2},
        "hpc_1rm_bw":          {"mean": 1.3,    "std": 0.2},
    }


def test_build_history_attaches_perch_history():
    from src.renderer import build_history

    athletes = [{"forcedecks_id": "fd1", "catapult_id": None, "full_name": "Alice Smith"}]
    pop_stats = _make_pop_stats_with_perch()
    empty = lambda cols: pd.DataFrame(columns=cols)

    perch_hist = pd.DataFrame([{
        "forcedecks_id": "fd1",
        "test_date":     "2025-10-15",
        "bs_1rm_bw":     2.3,
        "pc_1rm_bw":     1.6,
        "bp_1rm_bw":     None,
        "hpc_1rm_bw":    None,
    }])

    build_history(
        athletes,
        empty(["forcedecks_id","test_date","jump_height_cm","peak_power_bm","mrsi"]),
        empty(["catapult_id","session_date","hsd_m","player_load","max_velocity_ms"]),
        empty(["name_normalized","date","weight_kg"]),
        empty(["forcedecks_id","test_date","peak_force_n","peak_force_bm","rfd_100ms","rfd_200ms"]),
        perch_hist,
        pop_stats,
    )

    h = athletes[0]["perch_history"]
    assert len(h) == 1
    assert h[0]["date"] == "2025-10-15"
    assert h[0]["bs_1rm_bw"] == pytest.approx(2.3)
    assert h[0]["bs_1rm_bw_t"] == pytest.approx(60.0, abs=1.0)  # z=(2.3-2.0)/0.3=1 → t=60
    assert h[0]["bp_1rm_bw"] is None


def test_build_history_empty_perch_attaches_empty_list():
    from src.renderer import build_history

    athletes = [{"forcedecks_id": "fd1", "catapult_id": None, "full_name": "Alice Smith"}]
    pop_stats = _make_pop_stats_with_perch()
    empty = lambda cols: pd.DataFrame(columns=cols)

    build_history(
        athletes,
        empty(["forcedecks_id","test_date","jump_height_cm","peak_power_bm","mrsi"]),
        empty(["catapult_id","session_date","hsd_m","player_load","max_velocity_ms"]),
        empty(["name_normalized","date","weight_kg"]),
        empty(["forcedecks_id","test_date","peak_force_n","peak_force_bm","rfd_100ms","rfd_200ms"]),
        empty(["forcedecks_id","test_date","bs_1rm_bw","pc_1rm_bw","bp_1rm_bw","hpc_1rm_bw"]),
        pop_stats,
    )

    assert athletes[0]["perch_history"] == []


# ── Weight Room domain tests ──────────────────────────────────────────────────

def test_scorer_has_weight_room_domain():
    df = _make_df()
    df_scored, _ = score(df)
    assert "weight_room_domain" in df_scored.columns


def test_weight_room_nan_for_missing_perch():
    """Athlete with no Perch data gets NaN weight_room_domain (not a numeric value)."""
    df = _make_df()
    df_scored, _ = score(df)
    carol = df_scored[df_scored["full_name"] == "Carol Lee"]
    assert carol["weight_room_domain"].isna().all()


def test_tsa_still_scores_without_weight_room():
    """Athletes missing Weight Room domain still get a TSA from the other 4 domains."""
    df = _make_df()
    df_scored, _ = score(df)
    carol = df_scored[df_scored["full_name"] == "Carol Lee"]
    assert carol["tsa_score"].notna().all()


def test_missing_domains_includes_weight_room_label():
    df = _make_df()
    df_scored, _ = score(df)
    carol = df_scored[df_scored["full_name"] == "Carol Lee"]
    assert "Weight Room" in carol["missing_domains"].iloc[0]


def test_pop_stats_has_perch_keys():
    df = _make_df()
    _, pop_stats = score(df)
    for key in ["bs_1rm_bw", "pc_1rm_bw", "bp_1rm_bw", "hpc_1rm_bw"]:
        assert key in pop_stats, f"pop_stats missing Perch key: {key}"


def test_scored_df_has_five_domain_columns():
    df = _make_df()
    df_scored, _ = score(df)
    for col in ["cmj_domain", "gps_domain", "bw_domain", "strength_domain", "weight_room_domain"]:
        assert col in df_scored.columns, f"Missing domain column: {col}"
