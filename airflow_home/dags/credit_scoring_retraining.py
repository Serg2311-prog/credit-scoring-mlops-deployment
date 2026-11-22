"""
Credit scoring retraining DAG (Stage 7).

IMPORTANT:
- Heavy ML logic lives in `src.retraining` and is imported INSIDE task callables
  so DAG parsing stays light.
- Local compose uses SequentialExecutor + SQLite — NOT production.
- Never auto-promotes the production champion model.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator

# Parsing-time only: cheap defaults from env (no torch / evidently imports).
PROJECT_ROOT = Path(os.environ.get("CREDIT_SCORING_ROOT", "/opt/credit-scoring"))
DEFAULT_INPUT = os.environ.get(
    "RETRAIN_INPUT_PATH",
    str(PROJECT_ROOT / "artifacts" / "retraining" / "demo_input" / "retrain_input.csv"),
)
TRIGGER_MODES = os.environ.get("RETRAIN_TRIGGER_MODES", "scheduled")
DRY_RUN = os.environ.get("RETRAIN_DRY_RUN", "true").lower() in {"1", "true", "yes"}
PREPARE_HINT = (
    "Prepare synthetic demo input first: "
    "python -m src.retraining.cli prepare-demo-input "
    "(host) or mount artifacts/retraining/demo_input into the container."
)


def _optional_csv(path_value: str | None):
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_file():
        raise AirflowFailException(
            f"Configured CSV path does not exist: {path}. {PREPARE_HINT}"
        )
    import pandas as pd

    return pd.read_csv(path)


def check_input_data(**context):
    import hashlib
    from datetime import timezone

    from src.retraining.data_validation import check_input_data as _check
    from src.retraining.exceptions import DataValidationFailed

    conf = context["dag_run"].conf or {}
    input_path = Path(conf.get("input_path", DEFAULT_INPUT))
    if not input_path.is_file():
        raise AirflowFailException(
            f"Retraining input missing: {input_path}. {PREPARE_HINT} "
            "DAG will not pretend success without data."
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha1(str(input_path).encode("utf-8")).hexdigest()[:8]
    run_id = conf.get("run_id") or f"af-{stamp}-{digest}"
    try:
        result = _check(input_path)
    except DataValidationFailed as exc:
        raise AirflowFailException(f"Input validation failed: {exc}") from exc
    # Persist small meta only (no DataFrame in XCom).
    out = {
        "run_id": run_id,
        "input_path": str(input_path),
        "target": result["target"],
        "rows": result["rows"],
        "n_pos": result["n_pos"],
        "n_neg": result["n_neg"],
    }
    context["ti"].xcom_push(key="run_id", value=run_id)
    context["ti"].xcom_push(key="input_meta", value=out)
    path = (
        PROJECT_ROOT / "artifacts" / "retraining" / "airflow" / f"{run_id}_input.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return str(path)


def validate_data(**context):
    # Re-validate from path (idempotent).
    from src.retraining.data_validation import check_input_data as _check
    from src.retraining.exceptions import DataValidationFailed

    meta = context["ti"].xcom_pull(key="input_meta", task_ids="check_input_data")
    try:
        _check(Path(meta["input_path"]))
    except DataValidationFailed as exc:
        raise AirflowFailException(f"Re-validation failed: {exc}") from exc
    return "ok"


def check_retraining_trigger(**context):
    from src.retraining.triggers import evaluate_triggers

    conf = context["dag_run"].conf or {}
    modes = conf.get("modes", TRIGGER_MODES)
    modes_list = [m.strip() for m in str(modes).split(",") if m.strip()]
    if "force_scheduled" in conf:
        force = bool(conf["force_scheduled"])
    else:
        # scheduled mode means the window itself is the trigger; do not invent
        # scheduled fire when only drift/quality modes were requested.
        force = "scheduled" in modes_list

    run_id = context["ti"].xcom_pull(key="run_id", task_ids="check_input_data")
    decision_path = (
        PROJECT_ROOT / "artifacts" / "retraining" / "airflow" / f"{run_id}_trigger.json"
    )
    ref_path = conf.get("reference_path") or os.environ.get("RETRAIN_REFERENCE_PATH")
    cur_path = conf.get("current_path") or os.environ.get("RETRAIN_CURRENT_PATH")
    quality_report = conf.get("quality_report")
    drift_report = conf.get("drift_report")

    decision = evaluate_triggers(
        modes=modes,
        force_scheduled=force,
        reference_features=_optional_csv(ref_path),
        current_features=_optional_csv(cur_path),
        drift_report=drift_report if isinstance(drift_report, dict) else None,
        quality_report=quality_report if isinstance(quality_report, dict) else None,
        output_path=decision_path,
        save_html=False,
    )
    context["ti"].xcom_push(key="trigger_status", value=decision["status"])
    context["ti"].xcom_push(key="trigger_path", value=str(decision_path))
    if decision["status"] == "unavailable":
        raise AirflowFailException(
            f"Trigger inputs unavailable: {decision['message']}. "
            "Provide reference/current CSVs or verified monitoring reports; "
            "do not treat missing signals as a successful skip."
        )
    if decision["status"] == "skipped":
        return "skip_retraining"
    if decision["status"] == "triggered":
        return "prepare_training_data"
    raise AirflowFailException(f"Unexpected trigger status: {decision['status']}")


def prepare_training_data(**context):
    from src.retraining.config import run_dir
    from src.retraining.data_validation import check_input_data as _check
    from src.retraining.prepare import prepare_training_splits

    meta = context["ti"].xcom_pull(key="input_meta", task_ids="check_input_data")
    run_id = context["ti"].xcom_pull(key="run_id", task_ids="check_input_data")
    validated = _check(Path(meta["input_path"]))
    frame = validated.pop("validated_frame")
    directory = run_dir(run_id, dry_run=DRY_RUN)
    prep = prepare_training_splits(frame, validated["target"], run_directory=directory)
    context["ti"].xcom_push(key="prepare_meta", value=prep)
    context["ti"].xcom_push(key="run_directory", value=str(directory))
    return prep["train_path"]


def train_candidate(**context):
    import pandas as pd

    from src.retraining.trainer import train_candidate as _train

    prep = context["ti"].xcom_pull(key="prepare_meta", task_ids="prepare_training_data")
    directory = Path(
        context["ti"].xcom_pull(key="run_directory", task_ids="prepare_training_data")
    )
    train_df = pd.read_csv(prep["train_path"])
    meta = _train(train_df, prep["target"], run_directory=directory)
    # Keep XCom small.
    slim = {
        "backend": meta["backend"],
        "preprocessor_path": meta["preprocessor_path"],
        "model_path": meta["model_path"],
        "decision_threshold": meta["decision_threshold"],
    }
    context["ti"].xcom_push(key="candidate_meta", value=slim)
    return meta["model_path"]


def evaluate_candidate(**context):
    import pandas as pd

    from src.retraining.evaluation import evaluate_candidate as _eval

    prep = context["ti"].xcom_pull(key="prepare_meta", task_ids="prepare_training_data")
    directory = Path(
        context["ti"].xcom_pull(key="run_directory", task_ids="prepare_training_data")
    )
    cand = context["ti"].xcom_pull(key="candidate_meta", task_ids="train_candidate")
    holdout = pd.read_csv(prep["holdout_path"])
    result = _eval(
        holdout,
        prep["target"],
        candidate_meta=cand,
        run_directory=directory,
    )
    context["ti"].xcom_push(key="evaluation_status", value=result["status"])
    return result["status"]


def register_candidate(**context):
    from src.retraining.registry import register_candidate as _reg

    run_id = context["ti"].xcom_pull(key="run_id", task_ids="check_input_data")
    directory = context["ti"].xcom_pull(
        key="run_directory", task_ids="prepare_training_data"
    )
    cand = context["ti"].xcom_pull(key="candidate_meta", task_ids="train_candidate")
    status = context["ti"].xcom_pull(
        key="evaluation_status", task_ids="evaluate_candidate"
    )
    record = {
        "version": f"candidate-retrain-{run_id}",
        "run_id": run_id,
        "status": status,
        "artifact_dir": directory,
        "preprocessor_path": cand["preprocessor_path"],
        "model_path": cand["model_path"],
        "auto_promote": False,
        "promoted": False,
    }
    return _reg(record, dry_run=DRY_RUN)


def generate_report(**context):
    from src.retraining.pipeline import generate_report as _gen

    run_id = context["ti"].xcom_pull(key="run_id", task_ids="check_input_data")
    directory = Path(
        context["ti"].xcom_pull(key="run_directory", task_ids="prepare_training_data")
    )
    status = context["ti"].xcom_pull(
        key="evaluation_status", task_ids="evaluate_candidate"
    )
    payload = {
        "run_id": run_id,
        "status": status,
        "dry_run": DRY_RUN,
        "auto_promote": False,
        "source": "airflow",
        "run_directory": str(directory),
    }
    path = _gen(directory, payload)
    context["ti"].xcom_push(key="report_path", value=str(path))
    return str(path)


def notify_review_required(**context):
    from src.retraining.pipeline import notify_review_required as _notify

    directory = Path(
        context["ti"].xcom_pull(key="run_directory", task_ids="prepare_training_data")
    )
    status = context["ti"].xcom_pull(
        key="evaluation_status", task_ids="evaluate_candidate"
    )
    return _notify({"status": status, "reasons": []}, directory)


default_args = {
    "owner": "mlops",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": int(os.environ.get("RETRAIN_RETRIES", "1")),
    "retry_delay": timedelta(minutes=int(os.environ.get("RETRAIN_RETRY_MINUTES", "5"))),
}

with DAG(
    dag_id="credit_scoring_retraining",
    description="Stage 7 offline retraining (no auto-promote)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=os.environ.get("RETRAIN_SCHEDULE", "0 3 * * 1"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    tags=["credit-scoring", "retraining", "stage7"],
) as dag:
    start = EmptyOperator(task_id="start")
    t_check = PythonOperator(
        task_id="check_input_data", python_callable=check_input_data
    )
    t_validate = PythonOperator(task_id="validate_data", python_callable=validate_data)
    t_trigger = BranchPythonOperator(
        task_id="check_retraining_trigger",
        python_callable=check_retraining_trigger,
    )
    t_skip = EmptyOperator(task_id="skip_retraining")
    t_prepare = PythonOperator(
        task_id="prepare_training_data", python_callable=prepare_training_data
    )
    t_train = PythonOperator(task_id="train_candidate", python_callable=train_candidate)
    t_eval = PythonOperator(
        task_id="evaluate_candidate", python_callable=evaluate_candidate
    )
    t_reg = PythonOperator(
        task_id="register_candidate", python_callable=register_candidate
    )
    t_report = PythonOperator(
        task_id="generate_report", python_callable=generate_report
    )
    t_notify = PythonOperator(
        task_id="notify_review_required", python_callable=notify_review_required
    )
    end = EmptyOperator(task_id="end", trigger_rule="none_failed_min_one_success")

    start >> t_check >> t_validate >> t_trigger
    t_trigger >> t_skip >> end
    t_trigger >> t_prepare >> t_train >> t_eval >> t_reg >> t_report >> t_notify >> end
