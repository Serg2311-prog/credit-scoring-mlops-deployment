"""Quality degradation signals on labeled data (possible concept drift).

A drop in one metric is treated as a *signal requiring review*, not confirmed
concept drift. Data drift (feature distributions) is a separate check.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from src.monitoring.reports import utc_now_iso, write_report
from src.monitoring.thresholds import load_stage6_thresholds

METRIC_KEYS = ("roc_auc", "pr_auc", "precision", "recall", "f1")


def _class_counts(y: np.ndarray) -> dict[str, int]:
    y = np.asarray(y).astype(int)
    return {
        "n": int(len(y)),
        "n_pos": int(np.sum(y == 1)),
        "n_neg": int(np.sum(y == 0)),
        "n_unique": int(len(np.unique(y))),
    }


def compute_labeled_metrics(
    y_true,
    probability,
    *,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Safe metrics for binary scoring; handles missing labels / single class."""
    if y_true is None or probability is None:
        return {
            "status": "no_labels",
            "metrics": None,
            "class_counts": None,
            "message": "True labels are required for quality / concept-drift signals.",
        }

    y = np.asarray(y_true)
    if pd.isna(y).any() if hasattr(pd, "isna") else False:
        mask = ~pd.isna(y)
        y = y[mask]
        probability = np.asarray(probability)[mask]
    else:
        y = np.asarray(y_true)
        probability = np.asarray(probability, dtype=float)

    # Drop NaN probabilities.
    prob = np.asarray(probability, dtype=float)
    finite = np.isfinite(prob)
    y = np.asarray(y)[finite]
    prob = prob[finite]
    counts = _class_counts(y)

    if counts["n"] == 0:
        return {
            "status": "no_labels",
            "metrics": None,
            "class_counts": counts,
            "message": "Empty labeled sample after cleaning.",
        }

    if counts["n_unique"] < 2:
        return {
            "status": "single_class",
            "metrics": None,
            "class_counts": counts,
            "message": (
                "Only one class present; ROC-AUC/PR-AUC undefined. "
                "Not treated as confirmed concept drift."
            ),
        }

    pred = (prob >= threshold).astype(int)
    metrics = {
        "roc_auc": float(roc_auc_score(y, prob)),
        "pr_auc": float(average_precision_score(y, prob)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "threshold": float(threshold),
    }
    return {
        "status": "ok",
        "metrics": metrics,
        "class_counts": counts,
        "message": None,
    }


def run_concept_drift_check(
    *,
    reference_y,
    reference_proba,
    current_y,
    current_proba,
    threshold: float = 0.5,
    thresholds: dict[str, Any] | None = None,
    model_version: str | None = None,
    output_name: str = "concept_drift",
) -> dict[str, Any]:
    """
    Compare labeled quality vs a reference period.

    Returns a degradation *signal* when enough metrics drop past configured
    absolute thresholds. Does not assert confirmed concept drift from a single
    metric drop.
    """
    cfg = (thresholds or load_stage6_thresholds()).get("concept_drift", {})
    min_rows = int(cfg.get("min_rows", 50))
    min_pos = int(cfg.get("min_positives", 5))
    min_neg = int(cfg.get("min_negatives", 5))
    drops = {
        "roc_auc": float(cfg.get("roc_auc_drop", 0.03)),
        "pr_auc": float(cfg.get("pr_auc_drop", 0.03)),
        "f1": float(cfg.get("f1_drop", 0.05)),
    }
    require_drops = int(cfg.get("require_metric_drops", 2))
    started = utc_now_iso()

    ref = compute_labeled_metrics(reference_y, reference_proba, threshold=threshold)
    cur = compute_labeled_metrics(current_y, current_proba, threshold=threshold)

    base: dict[str, Any] = {
        "check_type": "concept_drift_signal",
        "distinction": (
            "Data drift = feature distribution change. "
            "This check = labeled quality change vs reference (possible concept drift)."
        ),
        "model_version": model_version,
        "decision_threshold": float(threshold),
        "thresholds": {
            "min_rows": min_rows,
            "min_positives": min_pos,
            "min_negatives": min_neg,
            "metric_drops": drops,
            "require_metric_drops": require_drops,
        },
        "reference": ref,
        "current": cur,
        "started_at_utc": started,
    }

    if ref["status"] != "ok" or cur["status"] != "ok":
        base.update(
            {
                "status": "not_evaluable",
                "degradation_signal": False,
                "confirmed_concept_drift": False,
                "dropped_metrics": [],
                "message": (
                    f"Cannot evaluate quality signal "
                    f"(reference={ref['status']}, current={cur['status']})."
                ),
                "finished_at_utc": utc_now_iso(),
            }
        )
        path = write_report(output_name, base, subdirectory="concept_drift")
        base["report_path"] = str(path)
        return base

    cur_counts = cur["class_counts"]
    if (
        cur_counts["n"] < min_rows
        or cur_counts["n_pos"] < min_pos
        or cur_counts["n_neg"] < min_neg
    ):
        base.update(
            {
                "status": "insufficient_data",
                "degradation_signal": False,
                "confirmed_concept_drift": False,
                "dropped_metrics": [],
                "message": (
                    f"Current sample too small or imbalanced for a reliable signal "
                    f"(n={cur_counts['n']}, pos={cur_counts['n_pos']}, "
                    f"neg={cur_counts['n_neg']}; need n>={min_rows}, "
                    f"pos>={min_pos}, neg>={min_neg})."
                ),
                "finished_at_utc": utc_now_iso(),
            }
        )
        path = write_report(output_name, base, subdirectory="concept_drift")
        base["report_path"] = str(path)
        return base

    ref_m = ref["metrics"]
    cur_m = cur["metrics"]
    dropped: list[dict[str, Any]] = []
    for key, drop in drops.items():
        delta = float(ref_m[key]) - float(cur_m[key])
        if delta >= drop:
            dropped.append(
                {
                    "metric": key,
                    "reference": float(ref_m[key]),
                    "current": float(cur_m[key]),
                    "drop": delta,
                    "drop_threshold": drop,
                }
            )

    signal = len(dropped) >= require_drops
    base.update(
        {
            "status": "ok",
            "metric_deltas": {
                key: float(ref_m[key]) - float(cur_m[key]) for key in drops
            },
            "dropped_metrics": dropped,
            "degradation_signal": bool(signal),
            # Never auto-confirm concept drift from offline metric drops alone.
            "confirmed_concept_drift": False,
            "message": (
                "Possible quality degradation signal — review data quality, "
                "labeling, and whether concept shift is plausible. "
                "Not confirmed concept drift."
                if signal
                else "No multi-metric degradation signal vs reference thresholds."
            ),
            "finished_at_utc": utc_now_iso(),
        }
    )
    path = write_report(output_name, base, subdirectory="concept_drift")
    base["report_path"] = str(path)
    return base
