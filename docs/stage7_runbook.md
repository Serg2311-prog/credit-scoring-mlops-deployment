# Stage 7 Runbook — Airflow Retraining Pipeline

## Scope

Offline, reproducible candidate retraining orchestrated for Apache Airflow.

- Engine: `src/retraining/` (runs on Windows without Airflow)
- DAG: `airflow_home/dags/credit_scoring_retraining.py` (folder name avoids shadowing the `airflow` Python package)
- Compose (optional Linux demo): `docker-compose.airflow.yml`
- **No automatic production promotion**

## Audit reuse map

| Need | Existing component |
| --- | --- |
| Schema validation | `src.data.validation.validate_dataframe` |
| Preprocessing | `fit_preprocessor` / `transform_features` |
| Metrics | `src.models.evaluate.compute_metrics` |
| Data / quality drift | Stage 6 `run_data_drift` / `run_concept_drift_check` |
| Registry | `models/model_registry.json` (atomic extend) |
| Synthetic data | `src.data.synthetic.make_synthetic_frame` |

Not present in-repo as working integrations: DVC remote, MLflow server. File-based tracking fallback is used; optional MLflow if enabled in config.

## Architecture

```
check_input_data → validate_data → check_retraining_trigger
                                      ├─ skip_retraining → end
                                      └─ prepare → train → evaluate → register
                                           → generate_report → notify_review → end
```

XCom carries only paths / small JSON (run_id, statuses). Models and DataFrames stay on disk under `artifacts/retraining/`.

## Triggers

| Mode | Fires when |
| --- | --- |
| `scheduled` | Planned / forced window |
| `data_drift` | Evidently drift share ≥ threshold (feature shift ≠ concept drift) |
| `quality_drop` | Multi-metric labeled degradation **signal** (never “confirmed concept drift”) |

No trigger → DAG branch `skip_retraining` (success, not failure).

## Gates (candidate vs champion)

Config: `configs/retraining/stage7.yaml`

- Absolute floors: `min_roc_auc`, `min_f1`
- Relative: max drop vs champion on the **same holdout**
- Outcomes: `accepted` | `rejected` | `needs_review`
- `auto_promote` always `false`

Holdout is never used for hyperparameter search. Train metrics are not used for release gates.

## CLI (Windows)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:OMP_NUM_THREADS = "1"

.\.venv\Scripts\python.exe -m src.retraining.cli validate-data --input data.csv
.\.venv\Scripts\python.exe -m src.retraining.cli check-triggers --modes scheduled
.\.venv\Scripts\python.exe -m src.retraining.cli dry-run --input data.csv --modes scheduled
.\.venv\Scripts\python.exe -m src.retraining.cli train-candidate --input data.csv --dry-run
.\.venv\Scripts\python.exe -m src.retraining.cli demo
```

Dry-run writes under `artifacts/retraining/dry_run/` and **does not** update production `models/model_registry.json`.

## Docker Airflow (optional)

```powershell
# Resource-heavy. Do not combine with observability stack by default.
docker compose -f docker-compose.airflow.yml up --build
# UI http://127.0.0.1:8080  (local demo user admin/admin)
```

Local stack: Airflow **2.9.3**, Python **3.12**, SequentialExecutor, SQLite. **Not production.**

## Manual promotion

1. Review `evaluation.json` / `retraining_report.json`.
2. Convert/export candidate artifacts if accepted (ONNX offline).
3. Explicitly update serving `MODEL_PATH` / `MODEL_VERSION`.
4. Manually set `production_champion` in `model_registry.json`.
5. Roll out via existing compose/k8s procedures.

## Failure recovery / idempotency

- Re-runs use new `run_id` folders → no artifact collisions.
- Registry replace-by-version is idempotent for the same candidate version.
- Atomic `os.replace` for registry writes; failed write removes temp file.
- Task failure stops downstream Airflow tasks; skip branch does not fail the DAG.

## Limits

- Default candidate backend is **logistic** (fast, deterministic, same preprocessor). MLP backend optional (`backend: mlp`) and heavier.
- Airflow E2E on this Windows host is optional and not required for unit validation.
- Do not install Airflow into the project Windows venv.
