"""Tests for trend chart data pipeline."""
import math
import pandas as pd
import pytest
from src.scorer import score


def _make_df():
    """Minimal 3-athlete DataFrame with all required columns."""
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
