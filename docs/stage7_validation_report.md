# Stage 7 Validation Report

**Date:** 2026-11-22 (stabilization pass)
**Environment:** Windows 11, PowerShell 5.1, Python 3.13 venv, 8 GB RAM, no GPU
**Docker / Airflow E2E:** **not executed** (compose `config` validated; full `up` not run)

## Defects confirmed (pre-fix audit)

| Defect | Impact |
| --- | --- |
| Fragile compose command (`&&` / `|| true` / `&`) | Unreliable DB/user/webserver/scheduler ordering and error handling |
| No reproducible demo input path | DAG could hit missing CSV without a documented prep step |
| Drift/quality triggers soft-skipped when inputs missing | Silent “success” without a real signal |
| MLP train vs score preprocessor / checkpoint mismatch risk | Candidate train could succeed while evaluation failed |
| Docs risk of implying Docker E2E without running it | Misleading validation status |

## Fixes applied

| Area | Change |
| --- | --- |
| Compose / image | `scripts/airflow/entrypoint.sh`: migrate → user → webserver + health wait → scheduler; Dockerfile `ENTRYPOINT`; compose demo CSV path |
| Demo data | `src/retraining/demo_data.py` + CLI `prepare-demo-input`; DAG fails if input missing |
| Triggers | Status `unavailable` when frames/reports missing or not evaluable; `TriggerUnavailable`; DAG `AirflowFailException` |
| MLP | Single full-train preprocessor; checkpoint `model_config`; aligned `_score_mlp`; unknown backends rejected at train |
| Docs | Runbook documents prep/launch; this report does **not** claim Docker E2E |

## Checks executed (stabilization)

| Check | Result |
| --- | --- |
| `pytest -q -x` (full) | **PASS** 148 passed, 1 skipped |
| `black --check src/retraining tests/retraining` | **PASS** (after format) |
| `flake8 src/retraining tests/retraining` | **PASS** |
| `git diff --check` | **PASS** (CRLF warnings only) |
| `docker compose -f docker-compose.airflow.yml config` | **PASS** |
| Docker Compose Airflow `up` / full DAG E2E | **NOT RUN** |
| Production `models/model_registry.json` | **unchanged** (restored; no promote) |

## New / updated tests

- Triggers: unavailable vs skipped vs fired (drift + quality), no fake concept-drift claims
- Pipeline: `TriggerUnavailable` when drift inputs missing; `TriggerSkip` when evaluated and none fired
- Demo input CLI/file + missing-path failure
- MLP train→score alignment (torch); unknown backend rejection

## Policy preserved

- `auto_promote: false`
- Production registry not mutated by this pass
- No real credit data in Git
- Stages 0–6 left intact unless required for Stage 7 imports

## Remaining limits

- Full Airflow-in-Docker E2E still optional / not validated here
- MLP candidate path needs torch in the runtime image if `backend: mlp` is selected (default remains `logistic`)
- Evidently drift on tiny synthetic frames can be non-deterministic; unit tests prefer explicit reports for hard asserts
