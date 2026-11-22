"""Stage 6 data-drift tests (synthetic frames only)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.monitoring.data_drift import run_data_drift, select_feature_columns
from src.schema import TARGET_COLUMN


def _base_frame(n: int = 80, seed: int = 0, shift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "LIMIT_BAL": rng.normal(100000 + shift, 20000, n),
            "AGE": rng.integers(21, 60, n) + int(shift // 10000),
            "SEX": rng.choice([1, 2], n),
            "EDUCATION": rng.choice([1, 2, 3], n),
            "MARRIAGE": rng.choice([1, 2], n),
            "PAY_0": rng.integers(-1, 3, n),
            "BILL_AMT1": rng.normal(20000, 5000, n),
            "PAY_AMT1": rng.normal(2000, 500, n),
            TARGET_COLUMN: rng.integers(0, 2, n),
        }
    )


def test_select_features_excludes_target():
    frame = _base_frame()
    num, cat = select_feature_columns(frame, target=TARGET_COLUMN)
    assert TARGET_COLUMN not in num
    assert TARGET_COLUMN not in cat
    assert "LIMIT_BAL" in num or "AGE" in num
    assert "SEX" in cat or "EDUCATION" in cat


def test_no_drift_on_identical_distribution():
    ref = _base_frame(90, seed=1)
    cur = ref.sample(frac=1.0, random_state=11).reset_index(drop=True)
    result = run_data_drift(
        ref, cur, target_column=TARGET_COLUMN, save_html=False, output_name="t_none"
    )
    assert result["status"] == "ok"
    assert result["target_excluded"] == TARGET_COLUMN
    assert TARGET_COLUMN not in result["features_analyzed"]
    assert result["data_drift_detected"] is False
    assert result["drift_share"] is not None
    assert float(result["drift_share"]) == 0.0


def test_synthetic_drift_detected():
    ref = _base_frame(100, seed=3, shift=0.0)
    cur = _base_frame(100, seed=3, shift=0.0)
    cur = cur.copy()
    cur["LIMIT_BAL"] = cur["LIMIT_BAL"] + 120000
    cur["AGE"] = cur["AGE"] + 12
    cur["EDUCATION"] = np.random.default_rng(9).choice([1, 2, 3, 4, 5, 6], len(cur))
    result = run_data_drift(
        ref, cur, target_column=TARGET_COLUMN, save_html=False, output_name="t_drift"
    )
    assert result["status"] == "ok"
    assert result["data_drift_detected"] is True
    assert result["drift_share"] >= 0.3


def test_missing_and_categorical_handled():
    ref = _base_frame(60, seed=4)
    cur = _base_frame(60, seed=5)
    ref.loc[0, "LIMIT_BAL"] = np.nan
    cur.loc[1, "EDUCATION"] = np.nan
    cur.loc[2, "SEX"] = None
    result = run_data_drift(
        ref, cur, target_column=TARGET_COLUMN, save_html=False, output_name="t_na"
    )
    assert result["status"] == "ok"
    assert (
        "EDUCATION" in result["categorical_features"]
        or "SEX" in result["categorical_features"]
    )


def test_insufficient_rows():
    ref = _base_frame(10, seed=6)
    cur = _base_frame(10, seed=7)
    result = run_data_drift(
        ref, cur, target_column=TARGET_COLUMN, save_html=False, output_name="t_small"
    )
    assert result["status"] == "insufficient_data"
    assert result["data_drift_detected"] is False


def test_report_files_written():
    ref = _base_frame(50, seed=8)
    cur = _base_frame(50, seed=8)
    result = run_data_drift(
        ref, cur, target_column=TARGET_COLUMN, save_html=False, output_name="t_report"
    )
    assert "report_path" in result
    from pathlib import Path

    assert Path(result["report_path"]).is_file()
