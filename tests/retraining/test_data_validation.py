"""Retraining data validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.synthetic import make_synthetic_frame
from src.retraining.data_validation import check_input_data, validate_retraining_frame
from src.retraining.exceptions import DataValidationFailed
from src.schema import TARGET_COLUMN


def test_valid_frame_ok():
    frame = make_synthetic_frame(80, seed=1)
    result = validate_retraining_frame(frame)
    assert result["status"] == "ok"
    assert result["target"] == TARGET_COLUMN
    assert result["target_excluded_from_features"] is True
    assert TARGET_COLUMN not in result["feature_columns"]


def test_empty_dataset(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DataValidationFailed, match="empty"):
        check_input_data(path)


def test_missing_target():
    frame = make_synthetic_frame(60, seed=2).drop(columns=[TARGET_COLUMN])
    with pytest.raises(DataValidationFailed, match="Target"):
        validate_retraining_frame(frame)


def test_single_class():
    frame = make_synthetic_frame(60, seed=3)
    frame[TARGET_COLUMN] = 0
    with pytest.raises(DataValidationFailed, match="single class"):
        validate_retraining_frame(frame)


def test_too_few_rows():
    frame = make_synthetic_frame(20, seed=4)
    with pytest.raises(DataValidationFailed, match="Insufficient rows"):
        validate_retraining_frame(frame)


def test_missing_file(tmp_path: Path):
    with pytest.raises(DataValidationFailed, match="not found"):
        check_input_data(tmp_path / "nope.csv")
