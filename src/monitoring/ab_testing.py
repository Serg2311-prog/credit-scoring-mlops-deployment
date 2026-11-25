"""Champion / Challenger A/B utilities (routing + offline same-holdout compare).

Production model is never auto-switched: promotion requires explicit confirmation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np

from src.config import PROJECT_ROOT, dump_json
from src.monitoring.concept_drift import compute_labeled_metrics
from src.monitoring.reports import monitoring_dir, utc_now_iso, write_report
from src.monitoring.thresholds import load_stage6_thresholds

GroupName = Literal["champion", "challenger"]


def assign_ab_group(
    unit_id: str | int,
    *,
    challenger_share: float = 0.2,
    salt: str = "credit-scoring-ab-v1",
) -> GroupName:
    """Deterministic hash routing for reproducible traffic splits."""
    if not 0.0 <= float(challenger_share) <= 1.0:
        raise ValueError("challenger_share must be in [0, 1]")
    digest = hashlib.sha256(f"{salt}:{unit_id}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return "challenger" if bucket < float(challenger_share) else "champion"


def assign_ab_groups(
    unit_ids,
    *,
    challenger_share: float = 0.2,
    salt: str = "credit-scoring-ab-v1",
) -> list[GroupName]:
    return [
        assign_ab_group(uid, challenger_share=challenger_share, salt=salt)
        for uid in unit_ids
    ]


def _bootstrap_metric_diff(
    y_true: np.ndarray,
    proba_a: np.ndarray,
    proba_b: np.ndarray,
    *,
    metric: str = "roc_auc",
    n_bootstrap: int = 200,
    alpha: float = 0.05,
    threshold: float = 0.5,
    random_state: int = 42,
) -> dict[str, Any]:
    rng = np.random.default_rng(random_state)
    y = np.asarray(y_true).astype(int)
    a = np.asarray(proba_a, dtype=float)
    b = np.asarray(proba_b, dtype=float)
    n = len(y)
    diffs: list[float] = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        ma = compute_labeled_metrics(y[idx], a[idx], threshold=threshold)
        mb = compute_labeled_metrics(y[idx], b[idx], threshold=threshold)
        if ma["status"] != "ok" or mb["status"] != "ok":
            continue
        diffs.append(float(mb["metrics"][metric]) - float(ma["metrics"][metric]))
    if not diffs:
        return {
            "metric": metric,
            "n_successful": 0,
            "mean_diff": None,
            "ci_low": None,
            "ci_high": None,
            "alpha": alpha,
        }
    arr = np.asarray(diffs, dtype=float)
    low = float(np.quantile(arr, alpha / 2))
    high = float(np.quantile(arr, 1 - alpha / 2))
    return {
        "metric": metric,
        "n_successful": int(len(arr)),
        "mean_diff": float(arr.mean()),
        "ci_low": low,
        "ci_high": high,
        "alpha": alpha,
        "interpretation": (
            "Positive mean_diff means challenger higher than champion on this metric. "
            "CI crossing 0 => uncertain advantage."
        ),
    }


def compare_models_offline(
    y_true,
    champion_proba,
    challenger_proba,
    *,
    champion_version: str,
    challenger_version: str,
    threshold: float = 0.5,
    thresholds: dict[str, Any] | None = None,
    output_name: str = "ab_offline",
    n_bootstrap: int = 200,
) -> dict[str, Any]:
    """
    Offline A/B quality comparison on the *same* labeled holdout.

    Prefer this over comparing online split groups when sample composition may differ.
    """
    cfg_all = thresholds or load_stage6_thresholds()
    ab_cfg = cfg_all.get("ab_testing", {})
    versions = cfg_all.get("versions", {})
    min_rows = int(ab_cfg.get("min_rows_offline", 40))
    alpha = float(ab_cfg.get("significance_alpha", 0.05))
    champion_version = champion_version or versions.get("champion", "champion")
    challenger_version = challenger_version or versions.get("challenger", "challenger")
    started = utc_now_iso()

    y = np.asarray(y_true)
    champ = compute_labeled_metrics(y, champion_proba, threshold=threshold)
    chall = compute_labeled_metrics(y, challenger_proba, threshold=threshold)

    result: dict[str, Any] = {
        "check_type": "ab_offline_same_holdout",
        "champion_version": champion_version,
        "challenger_version": challenger_version,
        "decision_threshold": float(threshold),
        "auto_promote": False,
        "promotion_requires_confirmation": True,
        "sample_size": int(len(y)),
        "min_rows_offline": min_rows,
        "champion": champ,
        "challenger": chall,
        "started_at_utc": started,
        "caveat": (
            "Online A/B groups may differ in composition; offline same-holdout "
            "comparison avoids that confound for quality ranking."
        ),
    }

    if len(y) < min_rows:
        result.update(
            {
                "status": "insufficient_data",
                "message": f"Need at least {min_rows} labeled rows for offline A/B.",
                "recommend_rollback_to_champion": True,
                "finished_at_utc": utc_now_iso(),
            }
        )
        path = write_report(output_name, result, subdirectory="ab_testing")
        result["report_path"] = str(path)
        return result

    if champ["status"] != "ok" or chall["status"] != "ok":
        result.update(
            {
                "status": "not_evaluable",
                "message": (
                    f"Metrics not computable "
                    f"(champion={champ['status']}, challenger={chall['status']})."
                ),
                "recommend_rollback_to_champion": True,
                "finished_at_utc": utc_now_iso(),
            }
        )
        path = write_report(output_name, result, subdirectory="ab_testing")
        result["report_path"] = str(path)
        return result

    cm = champ["metrics"]
    hm = chall["metrics"]
    deltas = {
        key: float(hm[key]) - float(cm[key])
        for key in ("roc_auc", "pr_auc", "precision", "recall", "f1")
    }
    bootstrap = {
        key: _bootstrap_metric_diff(
            y,
            champion_proba,
            challenger_proba,
            metric=key,
            n_bootstrap=n_bootstrap,
            alpha=alpha,
            threshold=threshold,
        )
        for key in ("roc_auc", "pr_auc", "f1")
    }

    # Conservative: challenger wins only if ROC-AUC and F1 point estimates improve
    # and ROC-AUC bootstrap CI lower bound is >= 0. Still never auto-promotes.
    challenger_better = (
        deltas["roc_auc"] > 0
        and deltas["f1"] > 0
        and bootstrap["roc_auc"]["ci_low"] is not None
        and bootstrap["roc_auc"]["ci_low"] >= 0
    )
    result.update(
        {
            "status": "ok",
            "metric_deltas_challenger_minus_champion": deltas,
            "bootstrap": bootstrap,
            "challenger_statistically_favored": bool(challenger_better),
            "recommend_rollback_to_champion": not bool(challenger_better),
            "message": (
                "Challenger looks favorable on same-holdout metrics, but production "
                "switch still requires explicit human confirmation."
                if challenger_better
                else (
                    "Keep / rollback to Champion unless a separate "
                    "review decides otherwise."
                )
            ),
            "finished_at_utc": utc_now_iso(),
        }
    )
    path = write_report(output_name, result, subdirectory="ab_testing")
    result["report_path"] = str(path)
    return result


def append_prediction_log(
    records: list[dict[str, Any]],
    *,
    experiment_id: str = "ab-default",
    path: Path | None = None,
) -> Path:
    """Append prediction rows with model_version / ab_group for later analysis."""
    out = path or (
        monitoring_dir() / "ab_testing" / f"{experiment_id}_predictions.jsonl"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as handle:
        for row in records:
            payload = {
                "experiment_id": experiment_id,
                "logged_at_utc": utc_now_iso(),
                **row,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return out


def production_model_registry_path() -> Path:
    return PROJECT_ROOT / "models" / "model_registry.json"


def write_model_registry(
    payload: dict[str, Any] | None = None,
    *,
    registry_path: Path | None = None,
    allow_production_write: bool = False,
) -> Path:
    """Write an experiment/ops model registry JSON.

    Default target is ``artifacts/monitoring/model_registry.json`` — never the
    production ``models/model_registry.json`` unless
    ``allow_production_write=True`` is set explicitly with that path.
    """
    cfg = load_stage6_thresholds()
    versions = cfg.get("versions", {})
    ab = cfg.get("ab_testing", {})
    registry = {
        "updated_at_utc": utc_now_iso(),
        "production_champion": versions.get("champion", "mlp-onnx-fp32-v1"),
        "challenger_candidate": versions.get("challenger", "challenger-candidate-v1"),
        "ab_enabled_default": False,
        "traffic_challenger_share": ab.get("traffic_challenger_share", 0.2),
        "hash_salt": ab.get("hash_salt", "credit-scoring-ab-v1"),
        "auto_promote": False,
        "rollback_target": versions.get("champion", "mlp-onnx-fp32-v1"),
        "notes": (
            "Promotion is manual. Set AB_ENABLED only after review; "
            "rollback = disable challenger and serve champion."
        ),
        **(payload or {}),
    }
    production = production_model_registry_path().resolve()
    path = (
        Path(registry_path)
        if registry_path is not None
        else monitoring_dir() / "model_registry.json"
    )
    resolved = path.resolve()
    if resolved == production and not allow_production_write:
        raise PermissionError(
            "Refusing to write production models/model_registry.json without "
            "allow_production_write=True. Use artifacts/ or a temp path for demos."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, registry)
    return path


def rollback_to_champion_plan() -> dict[str, Any]:
    """Documented rollback steps — does not mutate production automatically."""
    cfg = load_stage6_thresholds().get("versions", {})
    champion = cfg.get("champion", "mlp-onnx-fp32-v1")
    plan = {
        "action": "rollback_to_champion",
        "auto_executed": False,
        "champion_version": champion,
        "steps": [
            "Set AB_ENABLED=false (or unset).",
            "Ensure MODEL_PATH / MODEL_VERSION point to champion artifacts.",
            "Restart API / rollout previous Deployment revision if needed.",
            "Verify /health/ready and /model.",
        ],
        "generated_at_utc": utc_now_iso(),
    }
    path = write_report("rollback_plan", plan, subdirectory="ab_testing")
    plan["report_path"] = str(path)
    return plan
