"""DAG structure checks without requiring a running Airflow cluster."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

DAG_PATH = (
    Path(__file__).resolve().parents[2]
    / "airflow_home"
    / "dags"
    / "credit_scoring_retraining.py"
)

REQUIRED_TASKS = {
    "check_input_data",
    "validate_data",
    "check_retraining_trigger",
    "prepare_training_data",
    "train_candidate",
    "evaluate_candidate",
    "register_candidate",
    "generate_report",
    "notify_review_required",
    "skip_retraining",
}


def test_dag_file_exists_and_parses_ast():
    assert DAG_PATH.is_file()
    source = DAG_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in tree.body)
    # Guard: no obvious secrets in the DAG module
    assert "BEGIN PRIVATE KEY" not in source
    assert "AKIA" not in source
    assert "api_key" not in source.lower()


def test_dag_defines_required_task_ids():
    source = DAG_PATH.read_text(encoding="utf-8")
    for task_id in REQUIRED_TASKS:
        assert f'task_id="{task_id}"' in source or f"task_id='{task_id}'" in source


def test_dag_import_airflow_optional():
    airflow = pytest.importorskip("airflow")
    # Skip if a local folder shadowed the real distribution.
    if not hasattr(airflow, "DAG"):
        pytest.skip("apache-airflow not importable (package shadowing or missing)")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "credit_scoring_retraining_dag", DAG_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "dag")
    task_ids = set(module.dag.task_ids)
    assert REQUIRED_TASKS.issubset(task_ids)
