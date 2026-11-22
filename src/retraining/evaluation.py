"""Compare candidate vs champion on the SAME locked holdout."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from src.config import dump_json, load_json, nn_metadata_path
from src.models.evaluate import compute_metrics
from src.retraining.config import load_retraining_config
from src.retraining.exceptions import ChampionUnavailable
from src.retraining.trainer import score_candidate

ChampionScorer = Callable[[pd.DataFrame], np.ndarray]


def _bootstrap_delta(
    y: np.ndarray,
    cand: np.ndarray,
    champ: np.ndarray | None,
    *,
    metric: str,
    n_boot: int,
    alpha: float,
    threshold: float,
    seed: int,
) -> dict[str, Any]:
    if champ is None:
        return {"metric": metric, "available": False}
    rng = np.random.default_rng(seed)
    diffs: list[float] = []
    n = len(y)
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        try:
            mc = compute_metrics(y[idx], cand[idx], threshold=threshold)[metric]
            mh = compute_metrics(y[idx], champ[idx], threshold=threshold)[metric]
        except ValueError:
            continue
        diffs.append(float(mc) - float(mh))
    if not diffs:
        return {"metric": metric, "available": False, "n_successful": 0}
    arr = np.asarray(diffs, dtype=float)
    return {
        "metric": metric,
        "available": True,
        "n_successful": int(len(arr)),
        "mean_diff": float(arr.mean()),
        "ci_low": float(np.quantile(arr, alpha / 2)),
        "ci_high": float(np.quantile(arr, 1 - alpha / 2)),
        "alpha": alpha,
    }


def load_champion_holdout_metrics_fallback() -> dict[str, Any] | None:
    """Historical MLP test metrics from stage-1 metadata if present."""
    path = nn_metadata_path()
    if not path.is_file():
        return None
    try:
        meta = load_json(path)
        return meta.get("metrics", {}).get("test")
    except (OSError, ValueError):
        return None


def evaluate_candidate(
    holdout_df: pd.DataFrame,
    target: str,
    *,
    candidate_meta: dict[str, Any],
    run_directory: Path,
    champion_scorer: ChampionScorer | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_retraining_config()
    gates = cfg.get("gates", {})
    rt = cfg.get("retraining", {})
    threshold = float(rt.get("decision_threshold", 0.5))
    min_holdout = int(rt.get("min_holdout_rows", 20))
    seed = int(rt.get("random_state", 42))

    if len(holdout_df) < min_holdout:
        decision = "needs_review"
        result = {
            "status": decision,
            "reason": f"Holdout too small ({len(holdout_df)} < {min_holdout})",
            "auto_promote": False,
        }
        dump_json(run_directory / "evaluation.json", result)
        return result

    y = holdout_df[target].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        result = {
            "status": "needs_review",
            "reason": "Holdout has a single class; metrics unreliable",
            "auto_promote": False,
        }
        dump_json(run_directory / "evaluation.json", result)
        return result

    cand_proba = score_candidate(
        preprocessor_path=Path(candidate_meta["preprocessor_path"]),
        model_path=Path(candidate_meta["model_path"]),
        frame=holdout_df,
        target=target,
        backend=str(candidate_meta.get("backend", "logistic")),
    )
    cand_metrics = compute_metrics(y, cand_proba, threshold=threshold)

    champ_proba = None
    champ_metrics = None
    champion_status = "unavailable"
    champion_note = None
    if champion_scorer is not None:
        try:
            champ_proba = np.asarray(champion_scorer(holdout_df), dtype=float)
            if len(champ_proba) != len(y):
                raise ChampionUnavailable("Champion score length mismatch")
            champ_metrics = compute_metrics(y, champ_proba, threshold=threshold)
            champion_status = "scored_on_holdout"
        except Exception as exc:  # noqa: BLE001
            champion_status = "error"
            champion_note = str(exc)
    else:
        fallback = load_champion_holdout_metrics_fallback()
        if fallback:
            champ_metrics = fallback
            champion_status = "metadata_fallback_not_same_holdout"
            champion_note = (
                "Champion metrics taken from historical metadata — "
                "not same-holdout scores; gate uses absolute floors + review."
            )

    deltas = None
    if champ_metrics and champion_status == "scored_on_holdout":
        deltas = {
            key: float(cand_metrics[key]) - float(champ_metrics[key])
            for key in ("roc_auc", "pr_auc", "f1", "precision", "recall", "accuracy")
        }

    min_auc = float(gates.get("min_roc_auc", 0.65))
    min_f1 = float(gates.get("min_f1", 0.20))
    max_auc_drop = float(gates.get("max_roc_auc_drop_vs_champion", 0.02))
    max_f1_drop = float(gates.get("max_f1_drop_vs_champion", 0.05))
    review_auc_drop = float(gates.get("review_roc_auc_drop_vs_champion", 0.01))

    reasons: list[str] = []
    status = "accepted"

    if cand_metrics["roc_auc"] < min_auc:
        status = "rejected"
        reasons.append(
            f"Candidate ROC-AUC {cand_metrics['roc_auc']:.4f} < min_roc_auc {min_auc}"
        )
    if cand_metrics["f1"] < min_f1:
        status = "rejected"
        reasons.append(f"Candidate F1 {cand_metrics['f1']:.4f} < min_f1 {min_f1}")

    if deltas is not None and status != "rejected":
        # drop = champion - candidate = -delta
        auc_drop = -deltas["roc_auc"]
        f1_drop = -deltas["f1"]
        if auc_drop > max_auc_drop or f1_drop > max_f1_drop:
            status = "rejected"
            reasons.append(
                f"Degradation vs champion exceeds max "
                f"(auc_drop={auc_drop:.4f}, f1_drop={f1_drop:.4f})"
            )
        elif auc_drop > review_auc_drop or deltas["roc_auc"] < 0:
            status = "needs_review"
            reasons.append(
                "Candidate within soft band vs champion — manual review required"
            )
        else:
            reasons.append("Candidate meets absolute and relative gates on holdout")
    elif status != "rejected":
        if champion_status != "scored_on_holdout":
            status = "needs_review"
            reasons.append(
                "Champion not scored on the same holdout; "
                "absolute floors passed → needs_review (no auto-promote)"
            )
        else:
            reasons.append("Absolute floors passed")

    bootstrap = None
    if (
        bool(gates.get("require_bootstrap", False))
        and champ_proba is not None
        and status != "rejected"
    ):
        bootstrap = {
            key: _bootstrap_delta(
                y,
                cand_proba,
                champ_proba,
                metric=key,
                n_boot=int(gates.get("bootstrap_samples", 50)),
                alpha=float(gates.get("bootstrap_alpha", 0.05)),
                threshold=threshold,
                seed=seed,
            )
            for key in ("roc_auc", "f1")
        }

    result = {
        "status": status,
        "auto_promote": False,
        "promotion_requires_confirmation": True,
        "reasons": reasons,
        "holdout_rows": int(len(holdout_df)),
        "decision_threshold": threshold,
        "candidate_metrics": cand_metrics,
        "champion_metrics": champ_metrics,
        "champion_status": champion_status,
        "champion_note": champion_note,
        "deltas_candidate_minus_champion": deltas,
        "confusion_matrix": {
            "tn": cand_metrics["tn"],
            "fp": cand_metrics["fp"],
            "fn": cand_metrics["fn"],
            "tp": cand_metrics["tp"],
        },
        "bootstrap": bootstrap,
        "train_metrics_not_used_for_gate": True,
        "overwrites_production": False,
    }
    dump_json(run_directory / "evaluation.json", result)
    return result
