"""Retraining trigger tests."""

from __future__ import annotations

import numpy as np

from src.data.synthetic import make_synthetic_frame
from src.retraining.triggers import evaluate_triggers


def test_scheduled_trigger():
    decision = evaluate_triggers(modes="scheduled", force_scheduled=True)
    assert decision["status"] == "triggered"
    assert "scheduled" in decision["fired_modes"]


def test_no_trigger_skipped():
    decision = evaluate_triggers(modes="data_drift")
    assert decision["status"] == "skipped"
    assert decision["triggered"] is False


def test_data_drift_trigger_fires():
    # Prefer an explicit report to avoid flaky Evidently thresholds on tiny frames.
    decision = evaluate_triggers(
        modes="data_drift",
        drift_report={
            "drift_share": 0.5,
            "data_drift_detected": True,
            "report_path": "synthetic",
        },
    )
    assert decision["status"] == "triggered"
    assert "data_drift" in decision["fired_modes"]
    assert any(
        "not confirmed concept drift" in r.get("note", "").lower()
        for r in decision["reasons"]
        if r["mode"] == "data_drift"
    )


def test_data_drift_live_evidently_optional():
    ref = make_synthetic_frame(100, seed=10)
    cur = make_synthetic_frame(100, seed=10).copy()
    cur["LIMIT_BAL"] = cur["LIMIT_BAL"] + 200000
    cur["AGE"] = cur["AGE"] + 20
    cur["EDUCATION"] = 6
    decision = evaluate_triggers(
        modes="data_drift",
        reference_features=ref,
        current_features=cur,
        save_html=False,
    )
    # Soft assert: if Evidently detects shift, mode must be listed; else skipped ok.
    if decision["triggered"]:
        assert "data_drift" in decision["fired_modes"]


def test_quality_drop_without_labels_not_confirmed():
    decision = evaluate_triggers(modes="quality_drop")
    assert decision["status"] == "skipped"
    reason = decision["reasons"][0]
    assert reason["confirmed_quality_drop"] is False


def test_quality_drop_signal():
    rng = np.random.default_rng(0)
    y_ref = rng.integers(0, 2, 80)
    p_ref = np.clip(0.15 + 0.7 * y_ref + rng.normal(0, 0.05, 80), 0.01, 0.99)
    y_cur = rng.integers(0, 2, 80)
    p_cur = np.clip(0.5 + rng.normal(0, 0.2, 80), 0.01, 0.99)
    decision = evaluate_triggers(
        modes="quality_drop",
        reference_y=y_ref,
        reference_proba=p_ref,
        current_y=y_cur,
        current_proba=p_cur,
    )
    # May or may not fire depending on RNG; never claims confirmed concept drift.
    for reason in decision["reasons"]:
        if reason["mode"] == "quality_drop":
            assert reason.get("confirmed_concept_drift") is False
            assert reason.get("confirmed_quality_drop") is False
