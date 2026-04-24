"""Tests for Perch ingest and Weight Room domain."""
import os
import tempfile
import pytest
import duckdb
import pandas as pd


def test_perch_db_config_exists():
    """PERCH_DB must be importable from config."""
    from config import PERCH_DB
    assert PERCH_DB is not None
    assert str(PERCH_DB).endswith("perch.duckdb")
