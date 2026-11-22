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

    - scheduled: always fires when requested (force_scheduled or mode listed)
    - data_drift: feature distribution change (NOT concept drift proof)
    - quality_drop: multi-metric degradation *signal* with labels (not confirmed CD)

    Returns status ``triggered`` or ``skipped`` with rationale JSON.
    """
    cfg = cfg or load_retraining_config()
    trig = cfg.get("triggers", {})
    requested = _as_modes(modes, cfg)
    unknown = [m for m in requested if m not in VALID_TRIGGERS]
    if unknown:
        raise ValueError(f"Unknown trigger modes: {unknown}")

    reasons: list[dict[str, Any]] = []
    fired: list[str] = []

    if TRIGGER_SCHEDULED in requested or force_scheduled:
        fired.append(TRIGGER_SCHEDULED)
        reasons.append(
            {
                "mode": TRIGGER_SCHEDULED,
                "fired": True,
                "detail": "Scheduled / manual retraining window",
            }
        )

    if TRIGGER_DATA_DRIFT in requested:
        share_thr = float(trig.get("data_drift_share_threshold", 0.3))
        report = drift_report
        if report is None:
            if reference_features is None or current_features is None:
                reasons.append(
                    {
                        "mode": TRIGGER_DATA_DRIFT,
                        "fired": False,
                        "detail": "Skipped: reference/current frames not provided",
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
            detected = bool(report.get("data_drift_detected"))
            if share is None:
                detected = False
            elif float(share) >= share_thr:
                detected = True
            if detected:
                fired.append(TRIGGER_DATA_DRIFT)
            reasons.append(
                {
                    "mode": TRIGGER_DATA_DRIFT,
                    "fired": detected,
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
                reasons.append(
                    {
                        "mode": TRIGGER_QUALITY_DROP,
                        "fired": False,
                        "detail": (
                            "Skipped: labeled scores missing; "
                            "cannot claim confirmed quality drop"
                        ),
                        "confirmed_quality_drop": False,
                    }
                )
            else:
                # Align stage-6 thresholds temporarily via override dict.
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
            signal = bool(report.get("degradation_signal"))
            # Never treat as confirmed concept drift / hard proof.
            confirmed = False
            if signal and report.get("status") == "ok":
                fired.append(TRIGGER_QUALITY_DROP)
            reasons.append(
                {
                    "mode": TRIGGER_QUALITY_DROP,
                    "fired": signal and report.get("status") == "ok",
                    "degradation_signal": signal,
                    "confirmed_concept_drift": confirmed,
                    "confirmed_quality_drop": False,
                    "status": report.get("status"),
                    "message": report.get("message"),
                    "note": (
                        "Quality drop is a multi-metric signal requiring review; "
                        "not auto-proof of concept drift."
                    ),
                    "report_path": report.get("report_path"),
                }
            )

    triggered = len(fired) > 0
    decision = {
        "status": "triggered" if triggered else "skipped",
        "triggered": triggered,
        "fired_modes": fired,
        "requested_modes": requested,
        "reasons": reasons,
        "auto_promote": False,
        "message": (
            "Retraining trigger fired"
            if triggered
            else "No retraining trigger fired — workflow should skip without failure"
        ),
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        dump_json(output_path, decision)
        decision["decision_path"] = str(output_path)
    return decision
