"""Demo input preparation — synthetic only, never silent-success without file."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.retraining.cli import main as retraining_main
from src.retraining.data_validation import check_input_data
from src.retraining.demo_data import prepare_demo_input
from src.retraining.exceptions import DataValidationFailed


def test_prepare_demo_input_writes_valid_csv(tmp_path: Path):
    out = tmp_path / "retrain_input.csv"
    meta = prepare_demo_input(output_path=out, rows=80, seed=3)
    assert out.is_file()
    assert meta["synthetic_only"] is True
    assert meta["rows"] == 80
    validated = check_input_data(out)
    assert validated["rows"] == 80


def test_prepare_demo_input_cli(tmp_path: Path):
    out = tmp_path / "cli_demo.csv"
    rc = retraining_main(
        ["prepare-demo-input", "--output", str(out), "--rows", "60", "--seed", "1"]
    )
    assert rc == 0
    assert out.is_file()


def test_missing_input_fails_validation(tmp_path: Path):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(DataValidationFailed, match="not found"):
        check_input_data(missing)
