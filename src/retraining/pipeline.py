"""Coordinate retraining steps without mutating production artifacts."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import dump_json
from src.retraining.config import load_retraining_config, run_dir
from src.retraining.data_validation import check_input_data
from src.retraining.evaluation import evaluate_candidate
from src.retraining.exceptions import TriggerSkip, TriggerUnavailable
from src.retraining.mlflow_tracking import log_run
from src.retraining.prepare import prepare_training_splits
from src.retraining.registry import register_candidate
from src.retraining.trainer import train_candidate
from src.retraining.triggers import TRIGGER_NEW_DATA, evaluate_triggers


def _new_run_id(seed_material: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha1(seed_material.encode("utf-8")).hexdigest()[:8]
    return f"{stamp}-{digest}"


def generate_report(run_directory: Path, payload: dict[str, Any]) -> Path:
    path = run_directory / "retraining_report.json"
    dump_json(path, payload)
    return path


def notify_review_required(
    evaluation: dict[str, Any], run_directory: Path
) -> dict[str, Any]:
    needed = evaluation.get("status") in {"needs_review", "accepted"}
    # accepted still needs human promotion; rejected does not need promote review
    if evaluation.get("status") == "rejected":
        needed = False
    note = {
        "review_required": bool(needed) or evaluation.get("status") == "needs_review",
        "promotion_required_for_accepted": evaluation.get("status") == "accepted",
        "auto_promote": False,
        "message": (
            "Manual confirmation required before any production cutover. "
            "This notification does not block / wait forever."
        ),
        "evaluation_status": evaluation.get("status"),
        "reasons": evaluation.get("reasons"),
    }
    dump_json(run_directory / "review_notification.json", note)
    return note


def run_retraining_pipeline(
    input_path: Path,
    *,
    modes: str | list[str] | None = "scheduled",
    dry_run: bool = False,
    force_trigger: bool = False,
    cfg: dict[str, Any] | None = None,
    run_id: str | None = None,
    reference_path: Path | None = None,
    current_path: Path | None = None,
    quality_reference: Path | None = None,
    quality_current: Path | None = None,
    registry_path: Path | None = None,
    champion_scorer=None,
) -> dict[str, Any]:
    """
    Full offline retraining orchestration.

    dry_run=True: writes under artifacts/retraining/dry_run/ and does not
    update production models/model_registry.json.
    """
    cfg = cfg or load_retraining_config()
    input_path = Path(input_path)
    material = f"{input_path}:{modes}:{uuid.uuid4().hex if not dry_run else 'dry'}"
    rid = run_id or _new_run_id(material)
    directory = run_dir(rid, dry_run=dry_run, cfg=cfg)

    # 1–2. check + validate
    validated = check_input_data(input_path, cfg=cfg)
    frame: pd.DataFrame = validated.pop("validated_frame")
    dump_json(
        directory / "validate_data.json",
        {k: v for k, v in validated.items()},
    )

    # 3. triggers
    ref_df = pd.read_csv(reference_path) if reference_path else None
    cur_df = pd.read_csv(current_path) if current_path else None
    q_ref = pd.read_csv(quality_reference) if quality_reference else None
    q_cur = pd.read_csv(quality_current) if quality_current else None

    trigger = evaluate_triggers(
        modes=modes,
        force_scheduled=force_trigger
        or (modes == "scheduled" or modes == ["scheduled"]),
        input_path=input_path,
        reference_features=ref_df,
        current_features=cur_df,
        reference_y=(
            None if q_ref is None else q_ref.get("y", q_ref.get(validated["target"]))
        ),
        reference_proba=None if q_ref is None else q_ref.get("proba"),
        current_y=(
            None if q_cur is None else q_cur.get("y", q_cur.get(validated["target"]))
        ),
        current_proba=None if q_cur is None else q_cur.get("proba"),
        cfg=cfg,
        output_path=directory / "trigger_decision.json",
        save_html=False,
    )
    if trigger["status"] == "unavailable":
        report = {
            "run_id": rid,
            "status": "unavailable",
            "dry_run": dry_run,
            "trigger": trigger,
            "auto_promote": False,
            "run_directory": str(directory),
        }
        generate_report(directory, report)
        raise TriggerUnavailable(trigger["message"])
    if not trigger["triggered"]:
        report = {
            "run_id": rid,
            "status": "skipped",
            "dry_run": dry_run,
            "trigger": trigger,
            "auto_promote": False,
            "run_directory": str(directory),
        }
        generate_report(directory, report)
        raise TriggerSkip(trigger["message"])

    # 4. prepare
    prepare_meta = prepare_training_splits(
        frame,
        validated["target"],
        run_directory=directory,
        cfg=cfg,
    )
    train_df = pd.read_csv(prepare_meta["train_path"])
    holdout_df = pd.read_csv(prepare_meta["holdout_path"])

    # 5. train
    candidate_meta = train_candidate(
        train_df,
        validated["target"],
        run_directory=directory,
        cfg=cfg,
    )

    # 6. evaluate (same-holdout champion scorer when production ONNX is loadable)
    if champion_scorer is None:
        from src.retraining.champion import try_make_champion_scorer

        champion_scorer = try_make_champion_scorer(target=validated["target"])

    evaluation = evaluate_candidate(
        holdout_df,
        validated["target"],
        candidate_meta=candidate_meta,
        run_directory=directory,
        champion_scorer=champion_scorer,
        cfg=cfg,
    )

    # 7. register (candidate only; never promote)
    version = (
        f"{cfg.get('versions', {}).get('candidate_prefix', 'candidate-retrain')}-{rid}"
    )
    candidate_record = {
        "version": version,
        "run_id": rid,
        "backend": candidate_meta.get("backend"),
        "status": evaluation.get("status"),
        "metrics": evaluation.get("candidate_metrics"),
        "comparison": evaluation.get("deltas_candidate_minus_champion"),
        "artifact_dir": str(directory),
        "preprocessor_path": candidate_meta.get("preprocessor_path"),
        "model_path": candidate_meta.get("model_path"),
        "decision_reasons": evaluation.get("reasons"),
        "data_version": {
            "input_path": str(input_path),
            "train_rows": prepare_meta["train_rows"],
            "holdout_rows": prepare_meta["holdout_rows"],
            "random_state": prepare_meta["random_state"],
        },
    }
    registry_result = register_candidate(
        candidate_record,
        registry_path=registry_path,
        dry_run=dry_run,
    )

    # After a successful new_data-triggered train, refresh fingerprint baseline
    # so unchanged inputs do not retrain on the next check.
    if TRIGGER_NEW_DATA in (trigger.get("fired_modes") or []):
        from src.retraining.new_data import save_input_baseline

        save_input_baseline(input_path, note=f"post_retrain_{rid}")

    # tracking
    tracking = log_run(
        run_directory=directory,
        params={
            "backend": candidate_meta.get("backend"),
            "random_state": prepare_meta["random_state"],
            "dry_run": dry_run,
            "modes": str(modes),
        },
        metrics={
            f"candidate_{k}": v
            for k, v in (evaluation.get("candidate_metrics") or {}).items()
            if isinstance(v, (int, float))
        },
        tags={"run_id": rid, "status": evaluation.get("status")},
        artifact_paths=[
            str(directory / "evaluation.json"),
            str(directory / "candidate_train_meta.json"),
        ],
        cfg=cfg,
    )

    # 8–9 report + notify
    notification = notify_review_required(evaluation, directory)
    report = {
        "run_id": rid,
        "status": evaluation.get("status"),
        "workflow_status": "completed",
        "dry_run": dry_run,
        "auto_promote": False,
        "trigger": trigger,
        "validation": {k: v for k, v in validated.items()},
        "prepare": prepare_meta,
        "candidate": candidate_meta,
        "evaluation": evaluation,
        "registry": registry_result,
        "tracking": tracking,
        "notification": notification,
        "run_directory": str(directory),
        "manual_promotion_steps": [
            "Review evaluation.json and holdout metrics.",
            "Export/convert candidate if accepted (ONNX) offline.",
            "Update MODEL_PATH / MODEL_VERSION explicitly.",
            "Set production_champion in model_registry.json manually.",
            "Roll out via existing k8s/compose procedure.",
        ],
    }
    report_path = generate_report(directory, report)
    report["report_path"] = str(report_path)
    return report


def dry_run_pipeline(input_path: Path, **kwargs: Any) -> dict[str, Any]:
    return run_retraining_pipeline(input_path, dry_run=True, **kwargs)
