"""Stage 6 concept-drift / quality-signal tests."""

from __future__ import annotations

import numpy as np

from src.monitoring.concept_drift import (
    compute_labeled_metrics,
    run_concept_drift_check,
)


def test_metrics_calculation():
    y = np.array([0, 0, 1, 1, 0, 1, 0, 1])
    p = np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.7, 0.15, 0.85])
    out = compute_labeled_metrics(y, p, threshold=0.5)
    assert out["status"] == "ok"
    assert 0.0 <= out["metrics"]["roc_auc"] <= 1.0
    assert 0.0 <= out["metrics"]["pr_auc"] <= 1.0
    assert 0.0 <= out["metrics"]["f1"] <= 1.0


def test_no_labels():
    out = compute_labeled_metrics(None, np.array([0.1, 0.2]))
    assert out["status"] == "no_labels"


def test_single_class():
    y = np.zeros(40, dtype=int)
    p = np.linspace(0.1, 0.9, 40)
    out = compute_labeled_metrics(y, p)
    assert out["status"] == "single_class"
    assert out["metrics"] is None


def test_insufficient_data_for_signal():
    rng = np.random.default_rng(0)
    y_ref = rng.integers(0, 2, 80)
    p_ref = np.clip(0.2 + 0.6 * y_ref + rng.normal(0, 0.05, 80), 0.01, 0.99)
    y_cur = rng.integers(0, 2, 20)
    p_cur = np.clip(0.2 + 0.6 * y_cur + rng.normal(0, 0.05, 20), 0.01, 0.99)
    result = run_concept_drift_check(
        reference_y=y_ref,
        reference_proba=p_ref,
        current_y=y_cur,
        current_proba=p_cur,
        output_name="concept_small",
    )
    assert result["status"] == "insufficient_data"
    assert result["degradation_signal"] is False
    assert result["confirmed_concept_drift"] is False


def test_degradation_signal_requires_multiple_metrics():
    rng = np.random.default_rng(1)
    y_ref = rng.integers(0, 2, 100)
    p_ref = np.clip(0.15 + 0.7 * y_ref + rng.normal(0, 0.05, 100), 0.01, 0.99)
    y_cur = rng.integers(0, 2, 100)
    # Nearly random scores => large drop vs reference.
    p_cur = np.clip(0.5 + rng.normal(0, 0.2, 100), 0.01, 0.99)
    result = run_concept_drift_check(
        reference_y=y_ref,
        reference_proba=p_ref,
        current_y=y_cur,
        current_proba=p_cur,
        output_name="concept_signal",
    )
    assert result["status"] == "ok"
    assert result["confirmed_concept_drift"] is False
    # Signal may or may not fire depending on RNG; if it fires, must be multi-metric.
    if result["degradation_signal"]:
        assert len(result["dropped_metrics"]) >= 2
    # Sanity: reference metrics should beat near-random current on ROC.
    assert (
        result["reference"]["metrics"]["roc_auc"]
        > result["current"]["metrics"]["roc_auc"]
    )


def test_no_signal_when_quality_stable():
    rng = np.random.default_rng(2)
    y = rng.integers(0, 2, 120)
    p = np.clip(0.2 + 0.65 * y + rng.normal(0, 0.05, 120), 0.01, 0.99)
    result = run_concept_drift_check(
        reference_y=y[:60],
        reference_proba=p[:60],
        current_y=y[60:],
        current_proba=p[60:],
        output_name="concept_stable",
    )
    assert result["status"] == "ok"
    assert result["degradation_signal"] is False
    assert result["confirmed_concept_drift"] is False
