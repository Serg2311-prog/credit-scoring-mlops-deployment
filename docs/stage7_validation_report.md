# Stage 7 Validation Report

**Date:** 2026-11-22  
**Environment:** Windows 11, PowerShell 5.1, Python 3.13 venv, 8 GB RAM, no GPU  
**Docker / Airflow E2E:** **not executed** (resource constraint; intentionally skipped)

## Audit summary (pre-implementation)

| Area | Finding |
| --- | --- |
| Training | `src.nn.train_nn.train_mlp` writes production checkpoints — not called for candidates |
| Preprocessing | Reused `fit_preprocessor` / `transform_features` |
| Metrics | Reused `compute_metrics` |
| Validation | Reused Pandera `validate_dataframe` |
| Stage 6 | Reused data-drift + quality-signal for triggers |
| Registry | Extended `models/model_registry.json` without champion overwrite |
| MLflow / DVC | No working in-repo server/remote — file fallback + optional MLflow flag |
| Airflow in venv | Not installed (by design) |

## Checks executed locally

| Check | Result |
| --- | --- |
| `pytest tests/retraining` | **PASS** 22 + 1 skipped (Airflow import) |
| `pytest` (full) | **PASS** 137 + 1 skipped |
| `black --check` (stage 7 paths) | **PASS** |
| `flake8` (stage 7 paths) | **PASS** |
| `git diff --check` | **PASS** (CRLF warnings only) |
| CLI `python -m src.retraining.cli demo` | **PASS** (`status=needs_review`, `auto_promote=false`) |
| Reproducibility unit test | **PASS** |
| Docker Compose Airflow up | **NOT RUN** |
| Linux CI DAG parse job | **NOT RUN locally** (workflow added: `ci-airflow-dag.yml`) |

## Demo outcome

Synthetic dry-run produced `artifacts/retraining/dry_run/<run_id>/retraining_report.json` with:

- `auto_promote: false`
- production registry status: `dry_run_skipped_production_registry`
- decision `needs_review` (no same-holdout champion scorer in demo)

## Known gaps before commit

- Confirm GitHub Action `CI Airflow DAG` on push/PR (Linux).
- Optional manual `docker compose -f docker-compose.airflow.yml up --build` when RAM allows.
- Review that no large binary artifacts under `artifacts/retraining/` are staged for commit (gitignored via `artifacts/*`).
