"""Prepare train/holdout splits for candidate training (no target leakage)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

from src.config import dump_json
from src.retraining.config import load_retraining_config
from src.retraining.exceptions import DataValidationFailed
from src.schema import RAW_FEATURE_COLUMNS


def prepare_training_splits(
    frame: pd.DataFrame,
    target: str,
    *,
    run_directory: Path,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_retraining_config()
    rt = cfg.get("retraining", {})
    test_size = float(rt.get("test_size", 0.2))
    seed = int(rt.get("random_state", 42))
    min_holdout = int(rt.get("min_holdout_rows", 20))

    if target not in frame.columns:
        raise DataValidationFailed(f"Target '{target}' missing during prepare")

    feature_cols = [
        c for c in RAW_FEATURE_COLUMNS if c in frame.columns and c != target
    ]
    modeling = frame[feature_cols + [target]].copy()
    y = modeling[target].astype(int)
    if y.nunique() < 2:
        raise DataValidationFailed("Cannot stratify: single-class target")

    train_df, holdout_df = train_test_split(
        modeling,
        test_size=test_size,
        random_state=seed,
        stratify=y,
    )
    train_df = train_df.reset_index(drop=True)
    holdout_df = holdout_df.reset_index(drop=True)
    if len(holdout_df) < min_holdout:
        raise DataValidationFailed(
            f"Holdout too small: {len(holdout_df)} < min_holdout_rows={min_holdout}"
        )

    run_directory.mkdir(parents=True, exist_ok=True)
    train_path = run_directory / "train.csv"
    holdout_path = run_directory / "holdout.csv"
    train_df.to_csv(train_path, index=False)
    holdout_df.to_csv(holdout_path, index=False)

    meta = {
        "target": target,
        "feature_columns": feature_cols,
        "random_state": seed,
        "test_size": test_size,
        "train_rows": int(len(train_df)),
        "holdout_rows": int(len(holdout_df)),
        "train_path": str(train_path),
        "holdout_path": str(holdout_path),
        "train_pos": int((train_df[target] == 1).sum()),
        "holdout_pos": int((holdout_df[target] == 1).sum()),
        "note": (
            "Holdout is locked for final candidate evaluation only; "
            "not used for hyperparameter search."
        ),
    }
    dump_json(run_directory / "prepare_meta.json", meta)
    return meta
