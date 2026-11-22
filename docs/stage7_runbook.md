# Stage 7 Runbook — Airflow Retraining Pipeline

## Scope

Offline, reproducible candidate retraining orchestrated for Apache Airflow.

- Engine: `src/retraining/` (runs on Windows without Airflow)
- DAG: `airflow_home/dags/credit_scoring_retraining.py` (folder name avoids shadowing the `airflow` Python package)
- Compose (optional Linux demo): `docker-compose.airflow.yml`
- Entrypoint: `scripts/airflow/entrypoint.sh` (ordered migrate → user → webserver health → scheduler)
- **No automatic production promotion** (`auto_promote: false`)

## Required inputs

| Artifact | Path / how to get it | In Git? |
| --- | --- | --- |
| Retrain CSV | `artifacts/retraining/demo_input/retrain_input.csv` via `prepare-demo-input` | **No** (gitignored under `artifacts/`) |
| Config | `configs/retraining/stage7.yaml` | Yes |
| DAG | `airflow_home/dags/credit_scoring_retraining.py` | Yes |
| Optional drift frames | `RETRAIN_REFERENCE_PATH` / `RETRAIN_CURRENT_PATH` or DAG conf | No (local) |
| Optional quality/drift reports | DAG conf `quality_report` / `drift_report` dicts | No |

Missing `RETRAIN_INPUT_PATH` → DAG task `check_input_data` **fails** (not a silent skip).

## Prepare demo data (synthetic only)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path

.\.venv\Scripts\python.exe -m src.retraining.cli prepare-demo-input
# writes artifacts/retraining/demo_input/retrain_input.csv (+ meta JSON)
```

Do **not** commit real credit/PII rows. Demo CSV is reproducible (`seed`/`rows` flags) and lives under gitignored `artifacts/`.

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
                                      ├─ skip_retraining → end          (status=skipped)
                                      ├─ FAIL                           (status=unavailable)
                                      └─ prepare → train → evaluate → register
                                           → generate_report → notify_review → end
```

XCom carries only paths / small JSON (run_id, statuses). Models and DataFrames stay on disk under `artifacts/retraining/`.

## Triggers

| Mode | Fires when | If inputs missing |
| --- | --- | --- |
| `scheduled` | Planned / forced window | N/A |
| `data_drift` | Verified drift report or Evidently share ≥ threshold (feature shift ≠ concept drift) | `status=unavailable` → **fail** (CLI exit 3 / DAG fail) |
| `quality_drop` | Multi-metric labeled degradation **signal** (never “confirmed concept drift”) | `status=unavailable` → **fail** |

- `skipped` — modes evaluated with available inputs; none fired → branch `skip_retraining` (success).
- `unavailable` — required frames/reports absent or not evaluable → **must not** silent-succeed.
- Quality degradation is a **review signal**, not confirmed concept drift.

## Gates (candidate vs champion)

Config: `configs/retraining/stage7.yaml`

- Absolute floors: `min_roc_auc`, `min_f1`
- Relative: max drop vs champion on the **same holdout**
- Outcomes: `accepted` | `rejected` | `needs_review`
- `auto_promote` always `false`

Holdout is never used for hyperparameter search. Train metrics are not used for release gates.

## Backends

| Backend | Train | Score | Notes |
| --- | --- | --- | --- |
| `logistic` (default) | sklearn LogisticRegression | `predict_proba` | Fast, Windows-friendly |
| `mlp` | short torch train; preprocessor fit once on full train | same preprocessor + `model_config` checkpoint | Requires `torch`; train/eval dims stay aligned |

Unknown backends raise at train time (no “train ok / eval crash” split).

## CLI (Windows)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:OMP_NUM_THREADS = "1"

.\.venv\Scripts\python.exe -m src.retraining.cli prepare-demo-input
.\.venv\Scripts\python.exe -m src.retraining.cli validate-data --input artifacts/retraining/demo_input/retrain_input.csv
.\.venv\Scripts\python.exe -m src.retraining.cli check-triggers --modes scheduled
.\.venv\Scripts\python.exe -m src.retraining.cli dry-run --input artifacts/retraining/demo_input/retrain_input.csv --modes scheduled
.\.venv\Scripts\python.exe -m src.retraining.cli train-candidate --input artifacts/retraining/demo_input/retrain_input.csv --dry-run
.\.venv\Scripts\python.exe -m src.retraining.cli demo
```

Dry-run writes under `artifacts/retraining/dry_run/` and **does not** update production `models/model_registry.json`.

## Docker Airflow (optional local demo)

```powershell
# 1) Prepare host-side demo CSV (mounted into the container)
.\.venv\Scripts\python.exe -m src.retraining.cli prepare-demo-input

# 2) Validate compose file (no stack start)
docker compose -f docker-compose.airflow.yml config

# 3) Optional full stack — resource-heavy; do not combine with observability stack
docker compose -f docker-compose.airflow.yml up --build
# UI http://127.0.0.1:8080  (local demo user admin/admin)
```

Init order (entrypoint, no fragile `&&` / `|| true` / background chains for control flow):

1. `airflow db migrate`
2. Ensure admin user
3. Start webserver; wait until `/health` responds (or exit non-zero)
4. Run scheduler in foreground

Local stack: Airflow **2.9.3**, Python **3.12**, SequentialExecutor, SQLite. **Not production.** No Celery/Redis/Postgres/observability required.

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
- Missing input / unavailable triggers fail the task; skip branch does not fail the DAG.

## Limits

- Default candidate backend is **logistic**. MLP is supported when torch is installed; otherwise set `retraining.backend: logistic`.
- Airflow Docker E2E is optional and must not be claimed unless actually run.
- Do not install Airflow into the project Windows venv.
