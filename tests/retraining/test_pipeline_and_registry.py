"""Pipeline, evaluation, registry, reproducibility tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.synthetic import make_synthetic_frame
from src.retraining.evaluation import evaluate_candidate
from src.retraining.exceptions import TriggerSkip
from src.retraining.pipeline import dry_run_pipeline, run_retraining_pipeline
from src.retraining.prepare import prepare_training_splits
from src.retraining.exceptions import RegistryError
from src.retraining.registry import load_registry, register_candidate
from src.retraining.trainer import train_candidate
from src.schema import TARGET_COLUMN


@pytest.fixture
def synthetic_csv(tmp_path: Path) -> Path:
    path = tmp_path / "train_input.csv"
    make_synthetic_frame(120, seed=11).to_csv(path, index=False)
    return path


def test_dry_run_does_not_touch_production_registry(synthetic_csv: Path):
    report = dry_run_pipeline(
        synthetic_csv,
        modes="scheduled",
        force_trigger=True,
    )
    assert report["auto_promote"] is False
    assert report["dry_run"] is True
    assert report["registry"]["status"] == "dry_run_skipped_production_registry"


def test_full_train_registers_without_promoting(synthetic_csv: Path, tmp_path: Path):
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "production_champion": "mlp-onnx-fp32-v1",
                "auto_promote": False,
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )
    report = run_retraining_pipeline(
        synthetic_csv,
        modes="scheduled",
        force_trigger=True,
        dry_run=False,
        registry_path=registry,
        run_id="test-run-1",
    )
    updated = load_registry(registry)
    assert updated["production_champion"] == "mlp-onnx-fp32-v1"
    assert updated["auto_promote"] is False
    assert updated["latest_candidate"]["promoted"] is False
    assert report["auto_promote"] is False
    assert Path(report["run_directory"]).joinpath("candidate_model.joblib").is_file()


def test_skip_when_no_trigger(synthetic_csv: Path):
    with pytest.raises(TriggerSkip):
        run_retraining_pipeline(
            synthetic_csv,
            modes="data_drift",
            force_trigger=False,
            dry_run=True,
        )


def test_registry_atomic_and_idempotent(tmp_path: Path):
    path = tmp_path / "reg.json"
    path.write_text(
        json.dumps({"production_champion": "champ-v1", "candidates": []}),
        encoding="utf-8",
    )
    a = register_candidate(
        {"version": "cand-1", "status": "accepted", "run_id": "r1"},
        registry_path=path,
    )
    assert a["production_champion"] == "champ-v1"
    b = register_candidate(
        {"version": "cand-1", "status": "needs_review", "run_id": "r1"},
        registry_path=path,
    )
    data = load_registry(path)
    assert data["production_champion"] == "champ-v1"
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["status"] == "needs_review"
    assert b["auto_promote"] is False


def test_registry_fs_error(tmp_path: Path, monkeypatch):
    path = tmp_path / "reg.json"
    path.write_text(
        json.dumps({"production_champion": "c", "candidates": []}), encoding="utf-8"
    )

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("src.retraining.registry.os.replace", boom)
    with pytest.raises(RegistryError):
        register_candidate({"version": "x", "status": "accepted"}, registry_path=path)


def test_reproducibility(tmp_path: Path):
    frame = make_synthetic_frame(100, seed=21)
    d1 = tmp_path / "r1"
    d2 = tmp_path / "r2"
    m1 = prepare_training_splits(frame, TARGET_COLUMN, run_directory=d1)
    m2 = prepare_training_splits(frame, TARGET_COLUMN, run_directory=d2)
    assert m1["train_rows"] == m2["train_rows"]
    t1 = pd.read_csv(m1["train_path"])
    t2 = pd.read_csv(m2["train_path"])
    pd.testing.assert_frame_equal(t1, t2)
    c1 = train_candidate(t1, TARGET_COLUMN, run_directory=d1)
    c2 = train_candidate(t2, TARGET_COLUMN, run_directory=d2)
    assert c1["metrics"]["train"]["roc_auc"] == c2["metrics"]["train"]["roc_auc"]


def test_evaluation_reject_low_quality(tmp_path: Path):
    frame = make_synthetic_frame(100, seed=5)
    prep = prepare_training_splits(frame, TARGET_COLUMN, run_directory=tmp_path / "p")
    train_df = pd.read_csv(prep["train_path"])
    holdout = pd.read_csv(prep["holdout_path"])
    cand = train_candidate(train_df, TARGET_COLUMN, run_directory=tmp_path / "p")

    def bad_champion(_df: pd.DataFrame) -> np.ndarray:
        # Perfect champion scores → candidate relatively worse / still absolute may pass
        y = _df[TARGET_COLUMN].to_numpy()
        return np.clip(0.05 + 0.9 * y, 0.01, 0.99)

    # Force reject via ridiculous absolute floors
    cfg = {
        "retraining": {
            "decision_threshold": 0.5,
            "min_holdout_rows": 5,
            "random_state": 42,
        },
        "gates": {
            "min_roc_auc": 0.99,
            "min_f1": 0.99,
            "max_roc_auc_drop_vs_champion": 0.0,
            "max_f1_drop_vs_champion": 0.0,
            "review_roc_auc_drop_vs_champion": 0.0,
        },
    }
    result = evaluate_candidate(
        holdout,
        TARGET_COLUMN,
        candidate_meta=cand,
        run_directory=tmp_path / "p",
        champion_scorer=bad_champion,
        cfg=cfg,
    )
    assert result["status"] == "rejected"
    assert result["auto_promote"] is False


def test_artifacts_written(synthetic_csv: Path):
    report = dry_run_pipeline(synthetic_csv, modes="scheduled", force_trigger=True)
    run_dir = Path(report["run_directory"])
    assert (run_dir / "retraining_report.json").is_file()
    assert (run_dir / "evaluation.json").is_file()
    assert (run_dir / "trigger_decision.json").is_file()
