"""Retraining trigger decisions — reuses Stage 6 drift / quality semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.config import dump_json
from src.monitoring.concept_drift import run_concept_drift_check
from src.monitoring.data_drift import run_data_drift
from src.retraining.config import load_retraining_config
from src.schema import TARGET_COLUMN

TRIGGER_SCHEDULED = "scheduled"
TRIGGER_DATA_DRIFT = "data_drift"
TRIGGER_QUALITY_DROP = "quality_drop"
VALID_TRIGGERS = {TRIGGER_SCHEDULED, TRIGGER_DATA_DRIFT, TRIGGER_QUALITY_DROP}


def _as_modes(modes: Iterable[str] | str | None, cfg: dict[str, Any]) -> list[str]:
    if modes is None:
        enabled = cfg.get("triggers", {}).get("enabled_modes", [TRIGGER_SCHEDULED])
        return [str(m) for m in enabled]
    if isinstance(modes, str):
        parts = [p.strip() for p in modes.split(",") if p.strip()]
        return parts
    return [str(m) for m in modes]


def evaluate_triggers(
    *,
    modes: Iterable[str] | str | None = None,
    force_scheduled: bool = False,
    reference_features: pd.DataFrame | None = None,
    current_features: pd.DataFrame | None = None,
    reference_y=None,
    reference_proba=None,
    current_y=None,
    current_proba=None,
    drift_report: dict[str, Any] | None = None,
    quality_report: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
    output_path: Path | None = None,
    save_html: bool = False,
) -> dict[str, Any]:
    """
    Decide whether retraining should run.

    - scheduled: fires when requested
    - data_drift: feature distribution change (NOT concept drift proof)
    - quality_drop: multi-metric degradation *signal* (not confirmed concept drift)

    Returns status:
    - ``triggered`` — at least one mode fired
    - ``skipped`` — modes evaluated, none fired, inputs were available where needed
    - ``unavailable`` — a requested non-scheduled mode lacked required inputs/reports
      (callers must not treat this as a silent successful skip)
    """
    cfg = cfg or load_retraining_config()
    trig = cfg.get("triggers", {})
    requested = _as_modes(modes, cfg)
    unknown = [m for m in requested if m not in VALID_TRIGGERS]
    if unknown:
        raise ValueError(f"Unknown trigger modes: {unknown}")

    reasons: list[dict[str, Any]] = []
    fired: list[str] = []
    unavailable: list[str] = []

    if TRIGGER_SCHEDULED in requested or force_scheduled:
        fired.append(TRIGGER_SCHEDULED)
        reasons.append(
            {
                "mode": TRIGGER_SCHEDULED,
                "fired": True,
                "availability": "ok",
                "detail": "Scheduled / manual retraining window",
            }
        )

    if TRIGGER_DATA_DRIFT in requested:
        share_thr = float(trig.get("data_drift_share_threshold", 0.3))
        report = drift_report
        if report is None:
            if reference_features is None or current_features is None:
                unavailable.append(TRIGGER_DATA_DRIFT)
                reasons.append(
                    {
                        "mode": TRIGGER_DATA_DRIFT,
                        "fired": False,
                        "availability": "unavailable",
                        "detail": (
                            "Required reference/current feature frames (or "
                            "drift_report) were not provided; refusing silent skip"
                        ),
                        "note": (
                            "Data drift = feature distribution shift only; "
                            "not confirmed concept drift."
                        ),
                    }
                )
            else:
                report = run_data_drift(
                    reference_features,
                    current_features,
                    target_column=TARGET_COLUMN,
                    save_html=save_html,
                    output_name="retrain_trigger_data_drift",
                )
        if report is not None:
            share = report.get("drift_share")
            status = str(report.get("status") or "ok")
            if status == "insufficient_data":
                unavailable.append(TRIGGER_DATA_DRIFT)
                reasons.append(
                    {
                        "mode": TRIGGER_DATA_DRIFT,
                        "fired": False,
                        "availability": "unavailable",
                        "detail": report.get("message") or "insufficient_data",
                        "drift_share": share,
                        "report_path": report.get("report_path"),
                        "note": (
                            "Data drift check could not be completed; "
                            "not confirmed concept drift."
                        ),
                    }
                )
            else:
                detected = bool(report.get("data_drift_detected"))
                if share is not None and float(share) >= share_thr:
                    detected = True
                if detected:
                    fired.append(TRIGGER_DATA_DRIFT)
                reasons.append(
                    {
                        "mode": TRIGGER_DATA_DRIFT,
                        "fired": detected,
                        "availability": "ok",
                        "drift_share": share,
                        "threshold": share_thr,
                        "note": (
                            "Data drift = feature distribution shift only; "
                            "not confirmed concept drift."
                        ),
                        "report_path": report.get("report_path"),
                    }
                )

    if TRIGGER_QUALITY_DROP in requested:
        report = quality_report
        if report is None:
            if (
                reference_y is None
                or reference_proba is None
                or current_y is None
                or current_proba is None
            ):
                unavailable.append(TRIGGER_QUALITY_DROP)
                reasons.append(
                    {
                        "mode": TRIGGER_QUALITY_DROP,
                        "fired": False,
                        "availability": "unavailable",
                        "detail": (
                            "Labeled scores (y/proba for reference and current) "
                            "or quality_report required; cannot invent a signal"
                        ),
                        "confirmed_quality_drop": False,
                        "confirmed_concept_drift": False,
                        "note": (
                            "Missing inputs ≠ confirmed quality drop or concept drift"
                        ),
                    }
                )
            else:
                stage6_like = {
                    "concept_drift": {
                        "min_rows": int(trig.get("quality_min_rows", 50)),
                        "min_positives": int(trig.get("quality_min_positives", 5)),
                        "min_negatives": int(trig.get("quality_min_negatives", 5)),
                        "roc_auc_drop": float(trig.get("quality_roc_auc_drop", 0.03)),
                        "pr_auc_drop": float(trig.get("quality_pr_auc_drop", 0.03)),
                        "f1_drop": float(trig.get("quality_f1_drop", 0.05)),
                        "require_metric_drops": int(
                            trig.get("quality_require_metric_drops", 2)
                        ),
                    }
                }
                report = run_concept_drift_check(
                    reference_y=reference_y,
                    reference_proba=reference_proba,
                    current_y=current_y,
                    current_proba=current_proba,
                    thresholds=stage6_like,
                    output_name="retrain_trigger_quality",
                )
        if report is not None:
            q_status = str(report.get("status") or "")
            if q_status in {"not_evaluable", "insufficient_data", "no_labels"}:
                unavailable.append(TRIGGER_QUALITY_DROP)
                reasons.append(
                    {
                        "mode": TRIGGER_QUALITY_DROP,
                        "fired": False,
                        "availability": "unavailable",
                        "status": q_status,
                        "message": report.get("message"),
                        "confirmed_quality_drop": False,
                        "confirmed_concept_drift": False,
                        "note": (
                            "Quality signal not evaluable; "
                            "not confirmed concept drift."
                        ),
                        "report_path": report.get("report_path"),
                    }
                )
            else:
                signal = bool(report.get("degradation_signal"))
                if signal and q_status == "ok":
                    fired.append(TRIGGER_QUALITY_DROP)
                reasons.append(
                    {
                        "mode": TRIGGER_QUALITY_DROP,
                        "fired": bool(signal and q_status == "ok"),
                        "availability": "ok",
                        "degradation_signal": signal,
                        "confirmed_concept_drift": False,
                        "confirmed_quality_drop": False,
                        "status": q_status,
                        "message": report.get("message"),
                        "note": (
                            "Quality drop is a multi-metric signal requiring review; "
                            "not auto-proof of concept drift."
                        ),
                        "report_path": report.get("report_path"),
                    }
                )

    triggered = len(fired) > 0
    if triggered:
        status = "triggered"
        message = "Retraining trigger fired"
    elif unavailable:
        status = "unavailable"
        message = (
            "One or more requested trigger modes lack required inputs/results "
            f"({', '.join(unavailable)}); refusing silent success"
        )
    else:
        status = "skipped"
        message = "No retraining trigger fired — workflow should skip without failure"

    decision = {
        "status": status,
        "triggered": triggered,
        "fired_modes": fired,
        "unavailable_modes": unavailable,
        "requested_modes": requested,
        "reasons": reasons,
        "auto_promote": False,
        "message": message,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        dump_json(output_path, decision)
        decision["decision_path"] = str(output_path)
    return decision
