# BLOCK 8.1 — Final Acceptance Report

**Date:** 2026-11-25
**Baseline HEAD:** `871f467`
**Commit/push:** not performed
**Docker stacks:** stopped after checks

---

## 1. Root cause — production registry mutation

`python -m src.monitoring.cli demo` called `write_model_registry()` which defaulted to `models/model_registry.json`, rewriting production champion metadata during synthetic A/B demo.

## 2. Registry isolation fix

- Default registry path for monitoring writes: `artifacts/monitoring/`
- Demo writes `artifacts/monitoring/demo_model_registry.json`
- Writing `models/model_registry.json` raises `PermissionError` unless `allow_production_write=True`
- Dual demo runs: production SHA unchanged (`registry_immutability_demo.json`)
- Regression: `tests/monitoring/test_registry_immutability.py`

## 3. Security review — E2E log probe

| Check | Result |
| --- | --- |
| Production API route `/internal/e2e/log-error` | **Removed** |
| `ENABLE_E2E_LOG_PROBE` in API settings | **Removed** |
| Test injector | Separate `monitoring/e2e-log-probe/` + compose overlay `:9109` |
| Production compose services | No `e2e-log-probe` |
| Runtime OpenAPI / POST | 404 (`api_probe_absent_runtime.json`) |

## 4. Log-based alerting re-confirmed

Pipeline: `e2e-log-probe` ERROR JSON → Alloy (`config.e2e.alloy`) → Loki → ruler `APIErrorLogsDetected` → Alertmanager → webhook **firing** → **resolved**.
Evidence: `log_alert_firing.json`, `log_alert_resolved.json`, `webhook_after_log_alert.log`, `webhook_after_resolve.log`.
Production metric alert thresholds in `alerts.yml` not weakened (E2E uses overlay `alerts.e2e.yml` only).

## 5. Online A/B HTTP evidence

- Default: AB disabled on base compose
- Isolated: `docker-compose.ab.e2e.yml` — champion FP32 ONNX + challenger **existing** quantized ONNX (experimental INT8; no retrain)
- 1000 assignment IDs: share 0.293 vs 0.30; reproducible
- 150 HTTP predicts: both `mlp-onnx-fp32-v1` and `mlp-onnx-int8-exp-v1`; stable assignment for repeated ID
- Metrics: `ml_ab_experiment_samples_total{ab_group=champion|challenger}`
- Missing challenger path: ready; all responses champion; `auto_promote=false`
- Files: `online_ab_evidence.json`, `online_ab_challenger_unavailable.json`, `online_ab_stability_metrics.json`
- **Not** real-client traffic

**Offline A/B** = labeled quality comparison (demo CLI). **Online A/B** = routing verification under synthetic IDs.

## 6. Controlled concept drift experiment

`src/monitoring/concept_drift_experiment.py` + `concept_drift_experiment.json`:

| Scenario | X comparable | Data drift | Degradation |
| --- | --- | --- | --- |
| A Stable | yes | no | no |
| B Data drift | no | yes | no |
| C Concept (known P(Y\|X) flip, X identical) | yes (shift=0) | no | yes |
| D Perf degradation | yes | no | yes |

ROC-AUC drop alone is **not** claimed as real production concept drift.

## 7. Prometheus / Grafana drift metrics

- Exporter: `scripts/block8/drift_metrics_exporter.py` (`:9108`); missing/stale/corrupt → **503**, no invented zeros
- Prometheus scrape job `drift-metrics-exporter` — values e.g. share=`0.375`, detected=`1`, ROC/PR present
- Grafana dashboard queries filter `job="drift-metrics-exporter"` (API unset gauges still default to 0 — do not use unlabeled series)
- Evidence: `prometheus_ml_metrics_by_job.json`, `drift_metrics_scrape.txt`

## 8. Infrastructure metrics

cAdvisor on Docker Desktop: `container_cpu_usage_seconds_total`, `container_memory_usage_bytes` present; label keys observed: `__name__`, `id`, `instance`, `job`, `service`. **No** container `name` / compose-service labels. Limitation documented (`cadvisor_labels_evidence.json`). Live cloud K8s monitoring **NOT_EXECUTED**; YAML parse of manifests only.

## 9. Airflow retraining decision

Decision layer only on Block 8 artifacts (`e2e_airflow_triggers.py`):
stable→`skipped`; drift→`triggered`; degradation→`triggered`; invalid→`unavailable`; `auto_promote=false`; **no full retrain**.
Evidence: `airflow_trigger_decisions.json`.

## 10. New regression tests

- `test_registry_immutability.py`
- `test_e2e_probe_absent.py`
- `test_ab_challenger_fallback.py` / `test_ab_testing.py` (default off, deterministic)
- `test_concept_drift_experiment.py`
- `test_prometheus_export.py`
- `test_loki_alert_config.py` (ruler + no `request_id` stream labels + probe only in E2E compose)

Docker-free where possible; E2E kept behind markers / scripts.

## 11. Quality gates

| Gate | Result |
| --- | --- |
| `pytest -m "not k8s and not e2e"` | **231 passed**, 2 skipped |
| Monitoring/API targeted | **37 passed** |
| black (CI scope + block8 + e2e-log-probe) | **PASS** |
| flake8 (same scope) | **PASS** |
| docker compose config (obs E2E + AB E2E) | **PASS** |
| promtool check config/rules (+ e2e) | **PASS** |
| Loki `-verify-config` | **PASS** (`config is valid`) |
| Alloy `fmt` | **PASS** |
| K8s | YAML parse 30 OK; live cluster dry-run **BLOCKED** (no API server) |
| `git diff --check` | **PASS** |
| Secrets/PII scan on changed paths | **no hits** |

## 12. SHA256 before / after (all six unchanged)

| Artifact | SHA256 |
| --- | --- |
| `models/model_registry.json` | `ffea203ba3e3854f7817b64f533ef8ee616cca6217096e6c6ab701dba6ce204d` |
| `models/credit_scoring_nn.pt` | `d6e05563bb7790c34bf3e444db7c0e1d5ceea0aa92e26aa0b69f5d1f26d1c2ae` |
| `models/credit_scoring_nn.onnx` | `48051065162f98c0842f0f4bca80ce4105e343924a7b62001114c08adc7521a4` |
| `models/credit_scoring_nn.quant.onnx` | `e4ceed53c08ad0fe9592563f05e11069c4db6aa5c1172c7ff55945df21c65954` |
| `models/preprocessor.joblib` | `f949b92907853f09683ba0d82c9ec8aeb3d51bd6c06d37ffed82a8b867828b64` |
| `dvc.lock` | `eba4c5b671e05700fc925a6a616f7a8da69c5ccdc4e2514271b29e5d03f273da` |

GPU / Block 7 evidence bytes not modified.

## 13. Git status / diff stat

Uncommitted Block 8 + 8.1 working tree on `871f467`.
Tracked diffs include: `ab_testing.py`, `cli.py`, API schemas/main, alloy/loki, observability compose, stage5 runbook, requirements matrix.
Untracked: E2E overlays, e2e-log-probe, block8 scripts, new tests, Grafana drift dashboard, `results/block8/`, completion reports.
See `git_status_block81.txt`, `git_diff_stat_block81.txt`.

## 14. Remaining limitations

1. Docker Desktop cAdvisor: no per-container **name** labels
2. No live cloud Kubernetes / terraform apply
3. API still exposes unset `ml_data_drift_*` as 0 — use exporter job filter
4. Online A/B uses quantized ONNX as experimental challenger (compatible contract; not a separately trained challenger)
5. Airflow check is **decision layer only** (no Docker Airflow retrain in 8.1)
6. Commit/push deferred pending confirmation

## 15. Score justification

| Block | Max | Justified | Rationale |
| --- | --- | --- | --- |
| Monitoring (Этап 5) | **8** | **8** | Metrics, Grafana, Loki, metric+log alerts with firing/resolved, runbook; infra metrics partial on Desktop but honestly limited |
| Drift (Этап 6) | **7** | **7** | Evidently drift, degradation signal, controlled concept experiment, offline+online A/B, immutable production registry, exporter→Grafana, Airflow decision wiring |

Optional Seldon/shadow: **NOT_EXECUTED** (out of required scope).

---

**STOP:** awaiting confirmation. No commit/push. No Block 9.
