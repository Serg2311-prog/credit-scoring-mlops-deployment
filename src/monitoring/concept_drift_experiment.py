"""Reproducible synthetic experiments distinguishing data vs concept drift."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.metrics import average_precision_score

from src.monitoring.data_drift import run_data_drift
from src.monitoring.reports import write_report
from src.schema import TARGET_COLUMN

# Columns recognized by select_feature_columns / Evidently Stage-6 pipeline.
FEATURE_COLS = ["LIMIT_BAL", "AGE", "SEX", "EDUCATION"]


def _metrics(y_true: np.ndarray, proba: np.ndarray, *, threshold: float = 0.5) -> dict:
    y_pred = (proba >= threshold).astype(int)
    out: dict[str, float | None] = {
        "roc_auc": None,
        "pr_auc": None,
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
    }
    if len(np.unique(y_true)) >= 2:
        out["roc_auc"] = float(roc_auc_score(y_true, proba))
        out["pr_auc"] = float(average_precision_score(y_true, proba))
    return out


def _frame(x: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    data = {col: x[:, i] for i, col in enumerate(FEATURE_COLS)}
    data[TARGET_COLUMN] = y.astype(int)
    return pd.DataFrame(data)


def generate_concept_drift_scenarios(
    *,
    n: int = 400,
    seed: int = 42,
) -> dict[str, Any]:
    """Build A/B/C/D scenarios with known generative mechanisms.

    A Stable: same P(X), same P(Y|X)
    B Data drift: shift P(X), keep P(Y|X)
    C Concept drift: same P(X), flip/alter P(Y|X)
    D Performance degradation: noisy scores under stable labels
    """
    rng = np.random.default_rng(seed)
    # Synthetic but schema-compatible feature scales.
    x_ref = np.column_stack(
        [
            rng.normal(150000, 40000, n),  # LIMIT_BAL
            rng.integers(21, 65, n).astype(float),  # AGE
            rng.choice([1.0, 2.0], n),  # SEX
            rng.choice([1.0, 2.0, 3.0], n),  # EDUCATION
        ]
    )
    # True concept: y = 1{z(LIMIT_BAL)+0.5*z(AGE)+noise > 0}
    z0 = (x_ref[:, 0] - 150000) / 40000
    z1 = (x_ref[:, 1] - 40) / 12
    logits_ref = z0 + 0.5 * z1 + rng.normal(0, 0.35, n)
    y_ref = (logits_ref > 0).astype(int)

    # A: stable resample from same generative process
    x_a = np.column_stack(
        [
            rng.normal(150000, 40000, n),
            rng.integers(21, 65, n).astype(float),
            rng.choice([1.0, 2.0], n),
            rng.choice([1.0, 2.0, 3.0], n),
        ]
    )
    za0 = (x_a[:, 0] - 150000) / 40000
    za1 = (x_a[:, 1] - 40) / 12
    logits_a = za0 + 0.5 * za1 + rng.normal(0, 0.35, n)
    y_a = (logits_a > 0).astype(int)

    # B: data drift — shift P(X); same decision rule on new X
    x_b = x_ref.copy()
    x_b[:, 0] = x_b[:, 0] + 80000
    x_b[:, 1] = x_b[:, 1] + 8
    zb0 = (x_b[:, 0] - 150000) / 40000
    zb1 = (x_b[:, 1] - 40) / 12
    logits_b = zb0 + 0.5 * zb1 + rng.normal(0, 0.35, n)
    y_b = (logits_b > 0).astype(int)

    # C: concept drift — identical X as reference, inverted rule
    x_c = x_ref.copy()
    logits_c = -(z0 + 0.5 * z1) + rng.normal(0, 0.35, n)
    y_c = (logits_c > 0).astype(int)

    # Fit reference scorer on A-stable training slice
    clf = LogisticRegression(max_iter=500, random_state=seed)
    clf.fit(x_ref, y_ref)

    def score(x: np.ndarray) -> np.ndarray:
        return clf.predict_proba(x)[:, 1]

    # D: degradation — same X/y as stable, but scores corrupted
    x_d = x_a.copy()
    y_d = y_a.copy()
    proba_d = np.clip(score(x_d) * 0.2 + rng.uniform(0.3, 0.7, n), 0.01, 0.99)

    scenarios = {
        "A_stable": {
            "mechanism": "Same P(X) and P(Y|X) as reference generative process",
            "x": x_a,
            "y": y_a,
            "proba": score(x_a),
        },
        "B_data_drift": {
            "mechanism": "P(X) shifted (+1.5/+1.2 on x0/x1); P(Y|X) rule unchanged",
            "x": x_b,
            "y": y_b,
            "proba": score(x_b),
        },
        "C_concept_drift": {
            "mechanism": (
                "X identical to reference; P(Y|X) inverted "
                "(sign flip of linear rule) — synthetic known concept change"
            ),
            "x": x_c,
            "y": y_c,
            "proba": score(x_c),
        },
        "D_performance_degradation": {
            "mechanism": "Stable X/Y with deliberately corrupted score channel",
            "x": x_d,
            "y": y_d,
            "proba": proba_d,
        },
    }

    ref_frame = _frame(x_ref, y_ref)
    results: dict[str, Any] = {
        "seed": seed,
        "n": n,
        "feature_columns": FEATURE_COLS,
        "reference_target_rate": float(y_ref.mean()),
        "note": (
            "Controlled synthetic experiment. Falling ROC-AUC alone does not prove "
            "real-world concept drift; scenario C has a known P(Y|X) change."
        ),
        "scenarios": {},
    }

    for name, sc in scenarios.items():
        cur_frame = _frame(sc["x"], sc["y"])
        drift = run_data_drift(
            ref_frame,
            cur_frame,
            target_column=TARGET_COLUMN,
            save_html=False,
            output_name=f"concept_exp_{name}",
        )
        # Standardized mean shift (raw LIMIT_BAL units would dominate absolute diffs).
        ref_std = x_ref.std(axis=0) + 1e-8
        x_shift = float(
            np.mean(np.abs((sc["x"].mean(axis=0) - x_ref.mean(axis=0)) / ref_std))
        )
        metrics = _metrics(sc["y"], sc["proba"])
        ref_metrics = _metrics(y_ref, score(x_ref))
        degradation = False
        if ref_metrics["roc_auc"] is not None and metrics["roc_auc"] is not None:
            degradation = (ref_metrics["roc_auc"] - metrics["roc_auc"]) >= 0.05
        results["scenarios"][name] = {
            "mechanism": sc["mechanism"],
            "data_drift_detected": drift.get("data_drift_detected"),
            "data_drift_share": drift.get("drift_share"),
            "mean_abs_feature_shift": x_shift,
            "mean_abs_feature_shift_unit": "standardized_by_reference_std",
            "target_rate": float(sc["y"].mean()),
            "metrics": metrics,
            "reference_metrics": ref_metrics,
            "degradation_signal": degradation,
            "x_comparable_to_reference": x_shift < 0.35,
        }

    # Explicit assertions embedded for documentation / tests
    results["expectations"] = {
        "A_stable": {
            "data_drift_detected": False,
            "x_comparable_to_reference": True,
        },
        "B_data_drift": {
            "data_drift_detected": True,
            "x_comparable_to_reference": False,
        },
        "C_concept_drift": {
            "x_comparable_to_reference": True,
            "known_py_given_x_change": True,
        },
        "D_performance_degradation": {
            "degradation_signal": True,
        },
    }
    path = write_report(
        "concept_drift_experiment",
        results,
        subdirectory="concept_drift",
    )
    results["report_path"] = str(path)
    return results
