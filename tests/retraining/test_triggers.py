"""Retraining trigger tests — positive, negative, and unavailable paths."""

from __future__ import annotations

import numpy as np

from src.data.synthetic import make_synthetic_frame
from src.retraining.triggers import evaluate_triggers


def test_scheduled_trigger():
    decision = evaluate_triggers(modes="scheduled", force_scheduled=True)
    assert decision["status"] == "triggered"
    assert "scheduled" in decision["fired_modes"]
    assert decision["unavailable_modes"] == []


def test_data_drift_missing_inputs_unavailable():
    """Missing frames must not silent-skip when data_drift is requested."""
    decision = evaluate_triggers(modes="data_drift")
    assert decision["status"] == "unavailable"
    assert decision["triggered"] is False
    assert "data_drift" in decision["unavailable_modes"]
    assert any(r.get("availability") == "unavailable" for r in decision["reasons"])


def test_data_drift_below_threshold_skipped():
    decision = evaluate_triggers(
        modes="data_drift",
        drift_report={
            "status": "ok",
            "drift_share": 0.05,
            "data_drift_detected": False,
            "report_path": "synthetic",
        },
    )
    assert decision["status"] == "skipped"
    assert decision["triggered"] is False
    assert decision["unavailable_modes"] == []


def test_data_drift_trigger_fires():
    decision = evaluate_triggers(
        modes="data_drift",
        drift_report={
            "status": "ok",
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


def test_data_drift_insufficient_report_unavailable():
    decision = evaluate_triggers(
        modes="data_drift",
        drift_report={
            "status": "insufficient_data",
            "message": "too few rows",
            "drift_share": None,
        },
    )
    assert decision["status"] == "unavailable"
    assert "data_drift" in decision["unavailable_modes"]


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
    assert decision["status"] in {"triggered", "skipped"}
    assert decision["status"] != "unavailable"
    if decision["triggered"]:
        assert "data_drift" in decision["fired_modes"]


def test_quality_drop_without_labels_unavailable():
    decision = evaluate_triggers(modes="quality_drop")
    assert decision["status"] == "unavailable"
    reason = decision["reasons"][0]
    assert reason["confirmed_quality_drop"] is False
    assert reason["confirmed_concept_drift"] is False
    assert reason["availability"] == "unavailable"


def test_quality_drop_signal_never_claims_concept_drift():
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
    assert decision["status"] in {"triggered", "skipped", "unavailable"}
    for reason in decision["reasons"]:
        if reason["mode"] == "quality_drop":
            assert reason.get("confirmed_concept_drift") is False
            assert reason.get("confirmed_quality_drop") is False


def test_quality_drop_verified_report_fires():
    decision = evaluate_triggers(
        modes="quality_drop",
        quality_report={
            "status": "ok",
            "degradation_signal": True,
            "message": "synthetic quality signal",
        },
    )
    assert decision["status"] == "triggered"
    assert "quality_drop" in decision["fired_modes"]
    note = decision["reasons"][0].get("note", "").lower()
    assert "concept drift" in note
    assert "not" in note


def test_quality_drop_not_evaluable_unavailable():
    decision = evaluate_triggers(
        modes="quality_drop",
        quality_report={
            "status": "not_evaluable",
            "message": "labels missing in monitoring window",
        },
    )
    assert decision["status"] == "unavailable"
    assert decision["reasons"][0]["confirmed_concept_drift"] is False


def test_scheduled_plus_unavailable_drift_still_triggered():
    """Scheduled wins; unavailable companion mode is reported, does not block."""
    decision = evaluate_triggers(
        modes="scheduled,data_drift",
        force_scheduled=True,
    )
    assert decision["status"] == "triggered"
    assert "scheduled" in decision["fired_modes"]
    assert "data_drift" in decision["unavailable_modes"]
