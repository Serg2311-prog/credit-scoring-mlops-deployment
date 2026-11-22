"""MLP candidate train/score alignment (optional torch)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.data.synthetic import make_synthetic_frame
from src.retraining.exceptions import RetrainingError
from src.retraining.trainer import score_candidate, train_candidate
from src.schema import TARGET_COLUMN

torch = pytest.importorskip("torch")


def test_mlp_train_and_score_same_preprocessor(tmp_path: Path):
    frame = make_synthetic_frame(100, seed=21)
    cfg = {
        "retraining": {
            "backend": "mlp",
            "random_state": 21,
            "test_size": 0.25,
            "decision_threshold": 0.5,
            "mlp": {
                "epochs": 2,
                "early_stopping_patience": 2,
                "batch_size": 32,
                "hidden_dims": [32, 16],
                "dropout": 0.0,
                "learning_rate": 0.01,
                "weight_decay": 0.0,
                "num_threads": 1,
            },
        }
    }
    meta = train_candidate(
        frame, TARGET_COLUMN, run_directory=tmp_path / "mlp_run", cfg=cfg
    )
    assert meta["backend"] == "mlp"
    assert Path(meta["model_path"]).suffix == ".pt"
    proba = score_candidate(
        preprocessor_path=Path(meta["preprocessor_path"]),
        model_path=Path(meta["model_path"]),
        frame=frame,
        target=TARGET_COLUMN,
        backend="mlp",
    )
    assert len(proba) == len(frame)
    assert np.all(np.isfinite(proba))
    assert np.all((proba >= 0.0) & (proba <= 1.0))


def test_unknown_backend_rejected(tmp_path: Path):
    frame = make_synthetic_frame(60, seed=2)
    with pytest.raises(RetrainingError, match="Unknown retraining backend"):
        train_candidate(
            frame,
            TARGET_COLUMN,
            run_directory=tmp_path / "bad",
            cfg={"retraining": {"backend": "xgboost"}},
        )
