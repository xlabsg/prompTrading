import os
import tempfile
import pandas as pd
from backtest.artifacts import normalize_equity_curve_payload


def test_normalize_equity_curve_seconds_to_ms():
    payload = {
        "data": [
            {"timestamp": 1700000000, "equity": 10000.0, "drawdown": 0.0},
            {"timestamp": 1700003600, "equity": 10200.0, "drawdown": 0.0},
        ]
    }
    normalized = normalize_equity_curve_payload("/tmp", payload)
    assert normalized is not None
    assert normalized["data"][0]["timestamp"] == 1700000000000
    assert normalized["data"][1]["timestamp"] == 1700003600000


def test_normalize_equity_curve_already_ms():
    payload = {
        "data": [
            {"timestamp": 1700000000000, "equity": 10000.0, "drawdown": 0.0},
        ]
    }
    normalized = normalize_equity_curve_payload("/tmp", payload)
    assert normalized == payload


def test_normalize_equity_curve_rebuild_from_parquet():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create dummy equity.parquet
        df = pd.DataFrame(
            {
                "timestamp": [1700000000000, 1700003600000],
                "equity": [10000.0, 10500.0],
                "drawdown": [0.0, -0.05],
                "benchmark_equity": [10000.0, 10100.0],
            }
        )
        df.to_parquet(os.path.join(tmpdir, "equity.parquet"), index=False)

        # Legacy payload using row indices
        legacy_payload = {
            "data": [
                {"timestamp": 0, "equity": 10000.0, "drawdown": 0.0},
                {"timestamp": 1, "equity": 10500.0, "drawdown": 5.0},
            ]
        }
        rebuilt = normalize_equity_curve_payload(tmpdir, legacy_payload)
        assert rebuilt is not None
        assert len(rebuilt["data"]) == 2
        assert rebuilt["data"][0]["timestamp"] == 1700000000000
        assert rebuilt["data"][0]["benchmark_equity"] == 10000.0
        assert rebuilt["data"][1]["timestamp"] == 1700003600000
        assert rebuilt["data"][1]["benchmark_equity"] == 10100.0
        assert rebuilt["data"][1]["drawdown"] == 5.0
