# Stage 7 — Airflow Docker E2E Report (Block 4.1)

**Date:** 2026-11-24
**Status:** VERIFIED_LOCAL (Docker DagRun E2E + scheduler proof)
**Commit/push:** not performed.
**Cloud / terraform apply:** not executed.
**Production models / registry / baseline metrics:** unchanged (hashes below).

## Architecture

| Component | Value |
| --- | --- |
| Image | `credit-scoring-airflow:2.9.3` (`docker/Dockerfile.airflow`, includes `onnxruntime`) |
| Base | `apache/airflow:2.9.3-python3.12` |
| Executor | SequentialExecutor + SQLite |
| Entrypoint | `scripts/airflow/entrypoint.sh` |
| DAG id | `credit_scoring_retraining` |
| `max_active_runs` | **1** (DAG + compose `MAX_ACTIVE_RUNS_PER_DAG=1`) |
| Dry-run | `RETRAIN_DRY_RUN=true` |
| `auto_promote` | always `false` |
| Staff schedule | `RETRAIN_SCHEDULE=0 3 * * 1` in `docker-compose.airflow.yml` (override via env) |
| E2E schedule | `docker-compose.airflow.e2e.yml` sets `RETRAIN_SCHEDULE=None` |
| Documented cron | `configs/retraining/stage7.yaml` → `airflow.schedule_cron: "0 3 * * 1"` |

Graph: `start → check_input_data → validate_data → check_retraining_trigger` → (`skip_retraining` \| `prepare → train → evaluate → register → report → notify`) → `end`.

## Modes

| Mode | Compose / env | Behavior |
| --- | --- | --- |
| Staff / normal | `docker-compose.airflow.yml` only | Cron `0 3 * * 1`; scheduler creates `run_type=scheduled` DagRuns; `force_scheduled` inferred from run_type |
| Isolated E2E | base + `docker-compose.airflow.e2e.yml` | Schedule `None`; only scripted triggers; avoids collision with `max_active_runs=1` |

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m src.retraining.cli prepare-demo-input
docker compose -f docker-compose.airflow.yml -f docker-compose.airflow.e2e.yml config
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/airflow/e2e_docker.ps1
# Results: artifacts/retraining/e2e_diagnostics/e2e_results.json
# Evidence: artifacts/retraining/e2e_diagnostics/scenario_evidence/*.json
```

Staff stack (cron on): `docker compose -f docker-compose.airflow.yml up --build`

## Scheduler proof (automatic DagRun, no manual trigger)

Temporary cron `*/1 * * * *` on base compose (no E2E overlay). Observed without `airflow dags trigger`:

| Field | Value |
| --- | --- |
| DagRun ID | `scheduled__2026-11-24T09:35:00+00:00` |
| run_type | scheduled (Airflow-created) |
| Observed state | running (list-runs) |
| Restored | E2E overlay `RETRAIN_SCHEDULE=None`; staff default remains `0 3 * * 1` |

Same proof also observed earlier: `scheduled__2026-11-24T09:30:00+00:00`.

## Docker DagRuns (final PASS run, ~443 s wall)

| Scenario | DagRun ID | Type | Trigger reason | Dag state | Train? | Gate | Elapsed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A scheduled | `e2e_scheduled_20261124T094623Z` | manual | scheduled (`force_scheduled`) | success | yes | accepted | ~69s |
| A2 new_data | `e2e_new_data_20261124T094745Z` | manual | **new_data** (fingerprint change) | success | yes | accepted | ~68s |
| A2b unchanged | `e2e_new_data_skip_20261124T094853Z` | manual | new_data unchanged → skip | success | **no** | — | ~37s |
| B data_drift | `e2e_drift_20261124T094935Z` | manual | data_drift | success | yes | accepted | ~70s |
| C quality_drop | `e2e_quality_20261124T095045Z` | manual | quality_drop | success | yes | accepted | ~81s |
| D skip | `e2e_skip_20261124T095206Z` | manual | none (drift below thr) | success | **no** | — | ~38s |
| E missing input | `e2e_missing_20261124T095243Z` | manual | n/a | **failed** | **no** | — | ~22s |

Per-scenario task maps: `artifacts/retraining/e2e_diagnostics/scenario_evidence/`.

### new_data path (not force_retrain)

1. Baseline fingerprint via `baseline-input-state` on demo CSV.
2. CLI pre-check: `status=skipped` (unchanged).
3. Rewrite CSV with new synthetic seed → fingerprint change.
4. DagRun A2: `fired_modes` includes `new_data`; full train path.
5. Post-register baseline refresh → A2b: skip; train tasks not success.

### Skip confirmation (D, A2b)

Train-path tasks (`prepare_training_data`, `train_candidate`, `evaluate_candidate`, `register_candidate`) did **not** reach `success`; `skip_retraining` used.

### Missing input (E)

Failed at **`check_input_data`**; no train success; production hashes unchanged mid-scenario and after full suite.

## Quality gate (same-holdout champion)

Production ONNX + preprocessor scored on the **same** locked holdout as the candidate (`champion_status=scored_on_holdout`). Historical metadata is **not** used as equal comparison when the scorer loads.

Example (Scenario A, synthetic demo holdout — **not** production performance):

| Field | Value |
| --- | --- |
| Gate status | accepted |
| `auto_promote` | **false** |
| `dry_run` | true |
| Champion status | scored_on_holdout |
| Holdout rows | 24 |
| Candidate ROC-AUC / PR-AUC / F1 / accuracy | 0.9815 / 0.9583 / 0.9091 / 0.9583 (synthetic) |

If champion artifacts/runtime are incompatible, gate returns `needs_review` with an explicit reason (no fake same-holdout deltas). Candidate superiority is **not** required; absolute floors + relative drop caps apply. Promotion remains manual.

## Production integrity

SHA-256 before/after E2E (unchanged):

| File | SHA-256 |
| --- | --- |
| `models/model_registry.json` | `ffea203ba3e3854f7817b64f533ef8ee616cca6217096e6c6ab701dba6ce204d` |
| `models/credit_scoring_nn.onnx` | `48051065162f98c0842f0f4bca80ce4105e343924a7b62001114c08adc7521a4` |
| `models/preprocessor.joblib` | `f949b92907853f09683ba0d82c9ec8aeb3d51bd6c06d37ffed82a8b867828b64` |
| `models/baseline_metrics.json` | absent (null; not modified) |

`git diff -- models/` empty after the run.

## Block 4.1 code / compose changes (summary)

- Staff cron in compose; E2E overlay disables schedule.
- `new_data` fingerprint trigger + CLI `baseline-input-state`.
- DAG: `force_scheduled` only from conf or `run_type=scheduled`; pass `input_path`; ONNX champion scorer in evaluate; refresh fingerprint after new_data register.
- Dockerfile: `onnxruntime` for same-holdout scoring.
- Evidence writer in `e2e_docker.ps1`.

## Block 4.2 — pytest side-effect cleanup (2026-11-24)

Root causes fixed (not merely restored after runs):

1. `tests/monitoring/test_ab_testing.py::test_registry_and_rollback_plan` called `write_model_registry({"note_test": True})` → wrote production `models/model_registry.json`. Now uses `registry_path=tmp_path/...`.
2. `tests/test_dvc_pipeline.py::test_dvc_repro_and_pull_roundtrip` ran `dvc repro --force` in the repo root → rewrote `dvc.lock` with trailing whitespace. Now runs in an isolated tmp workspace and asserts repo `dvc.lock` bytes unchanged.

Dual local verification (`scripts/ci/dual_verify_block42.py`): two consecutive `pytest -m "not k8s and not e2e"` + black + flake8 with stable SHA-256 for registry / ONNX / preprocessor / `dvc.lock`.

## Remaining limits

1. Local compose is **not** production Airflow (no Celery/Postgres/HA).
2. Holdout metrics above are on **synthetic** demo data only.
3. Docker E2E B/C use controlled conf reports for determinism.
4. **VERIFIED_CI** for compose E2E not claimed (GHA has DAG parse only).
5. Do not co-run observability + Airflow + kind on 8 GB RAM.

## Score (Stage 7 / 5 ТЗ)

**~5 / 5** for local Docker scope: cron + E2E off, scheduler-created DagRun, new_data detect/train/skip, same-holdout champion gate with `auto_promote=false`, skip/fail evidence, production hashes stable.

## Historical Stage 7 validation snapshot (2026-11-22)

Early Stage 7 validation focused on compose/command defects and demo-input reproducibility before the Docker E2E closeout documented above.
