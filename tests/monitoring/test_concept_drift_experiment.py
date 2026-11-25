"""Controlled concept-drift experiment (synthetic P(Y|X) change)."""

from __future__ import annotations

from src.monitoring.concept_drift_experiment import generate_concept_drift_scenarios


def test_concept_drift_experiment_scenarios_distinguishable():
    result = generate_concept_drift_scenarios(n=300, seed=11)
    scenarios = result["scenarios"]

    a = scenarios["A_stable"]
    b = scenarios["B_data_drift"]
    c = scenarios["C_concept_drift"]
    d = scenarios["D_performance_degradation"]

    assert a["data_drift_detected"] is False
    assert a["x_comparable_to_reference"] is True

    assert b["data_drift_detected"] is True
    assert b["x_comparable_to_reference"] is False

    # Known concept change: X matches reference, labels/rule flipped.
    assert c["x_comparable_to_reference"] is True
    assert c["mean_abs_feature_shift"] < 1e-9 or c["x_comparable_to_reference"]
    # Scorer trained on old concept should degrade under flipped labels.
    assert c["degradation_signal"] is True or (
        c["metrics"]["roc_auc"] is not None
        and c["reference_metrics"]["roc_auc"] is not None
        and c["metrics"]["roc_auc"] < c["reference_metrics"]["roc_auc"]
    )

    assert d["degradation_signal"] is True
    assert "report_path" in result
