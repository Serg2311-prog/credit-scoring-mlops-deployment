"""Stage 7 retraining engine (offline; no auto-promote).

Keep this package init import-light so Airflow task modules can import
`data_validation` / `triggers` without pulling matplotlib/torch via pipeline.
"""

from __future__ import annotations

__all__ = [
    "dry_run_pipeline",
    "evaluate_triggers",
    "run_retraining_pipeline",
]


def __getattr__(name: str):
    if name == "dry_run_pipeline":
        from src.retraining.pipeline import dry_run_pipeline

        return dry_run_pipeline
    if name == "run_retraining_pipeline":
        from src.retraining.pipeline import run_retraining_pipeline

        return run_retraining_pipeline
    if name == "evaluate_triggers":
        from src.retraining.triggers import evaluate_triggers

        return evaluate_triggers
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
