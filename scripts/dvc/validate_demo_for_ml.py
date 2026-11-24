"""Prove DVC demo splits are usable for training/evaluation (no prod model writes)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.data.validation import validate_dataframe
from src.schema import RAW_FEATURE_COLUMNS, TARGET_COLUMN, detect_target


def _metrics(y_true, proba, threshold: float = 0.5) -> dict[str, float]:
    y_true = np.asarray(y_true).astype(int)
    proba = np.asarray(proba, dtype=float)
    pred = (proba >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_true, pred)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", required=True)
    parser.add_argument("--test", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    train_raw = validate_dataframe(pd.read_csv(args.train))
    test_raw = validate_dataframe(pd.read_csv(args.test))
    target = detect_target(train_raw.columns, preferred=TARGET_COLUMN)
    feature_cols = [c for c in RAW_FEATURE_COLUMNS if c in train_raw.columns]

    x_train = train_raw.loc[:, feature_cols]
    y_train = train_raw[target].astype(int)
    x_test = test_raw.loc[:, feature_cols]
    y_test = test_raw[target].astype(int)

    x_fit, x_val, y_fit, y_val = train_test_split(
        x_train, y_train, test_size=0.25, random_state=int(args.seed), stratify=y_train
    )
    pipe = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=400, random_state=int(args.seed))),
        ]
    )
    pipe.fit(x_fit, y_fit)
    val_metrics = _metrics(y_val.to_numpy(), pipe.predict_proba(x_val)[:, 1])

    pipe.fit(x_train, y_train)
    test_metrics = _metrics(y_test.to_numpy(), pipe.predict_proba(x_test)[:, 1])

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "synthetic_only": True,
        "writes_production_models": False,
        "train_rows": int(len(train_raw)),
        "test_rows": int(len(test_raw)),
        "n_features": int(len(feature_cols)),
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "note": (
            "Smoke fit on DVC demo splits only. Does not overwrite "
            "models/*.onnx / model_registry.json."
        ),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
