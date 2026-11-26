# Stage 6 / Block 8 + 8.1 — Drift & model management completion report

**Date:** 2026-11-25
**Environment:** local Python `.venv` (Evidently 0.7.x); isolated Docker for online A/B
**Commit/push:** not performed

## TZ mapping (Этап 6 — max 7)

| Requirement | Status |
| --- | --- |
| Evidently data drift | **VERIFIED** (`pytest tests/monitoring` + `python -m src.monitoring.cli demo`) |
| Concept drift / performance decay | **VERIFIED** degradation signal + controlled synthetic P(Y\|X) experiment (`results/block8/concept_drift_experiment.json`) |
| Drift dashboards | **VERIFIED** offline gauges via `drift-metrics-exporter:9108` → Prometheus → Grafana (`job="drift-metrics-exporter"`) |
| Seldon Core | **NOT_EXECUTED** (optional) |
| Offline A/B quality evaluation | **VERIFIED** (demo CLI; `auto_promote=false`) |
| Online dual-ONNX A/B routing | **VERIFIED** isolated compose (`docker-compose.ab.e2e.yml`); default AB disabled; ≥1000 assignment IDs; HTTP both branches |
| Shadow deployment | **NOT_EXECUTED** (optional) |

## Production registry immutability (Block 8.1)

| Item | Status |
| --- | --- |
| Root cause | `cli demo` → `write_model_registry()` defaulted to `models/model_registry.json` |
| Fix | Demo writes `artifacts/monitoring/demo_model_registry.json`; production path raises `PermissionError` unless `allow_production_write=True` |
| Evidence | Dual demo runs; SHA256 production registry unchanged (`results/block8/registry_immutability_demo.json`) |
| Regression | `tests/monitoring/test_registry_immutability.py` |

## Controlled concept-drift experiment (A–D)

| Scenario | Mechanism | X comparable | Drift detected | Degradation |
| --- | --- | --- | --- | --- |
| A Stable | Same P(X), same P(Y\|X) | yes | no | no |
| B Data drift | Shift P(X), same rule | no | yes | no |
| C Concept drift | Identical X, inverted P(Y\|X) | yes (shift=0) | no | yes (known synthetic) |
| D Perf degradation | Stable X/Y, corrupted scores | yes | no | yes |

**Note:** Falling ROC-AUC alone is **not** proof of real-world concept drift; scenario C has a known generative flip.

## Online A/B (synthetic HTTP — not real clients)

- Champion: `credit_scoring_nn.onnx` (`mlp-onnx-fp32-v1`)
- Challenger: existing `credit_scoring_nn.quant.onnx` as experimental INT8 (`mlp-onnx-int8-exp-v1`)
- Assignment 1000 IDs: challenger share 0.293 vs configured 0.30 (within ±0.05); reproducible
- HTTP 150 requests: both versions seen; Prometheus `ml_ab_experiment_samples_total{ab_group=…}`
- Missing challenger path: ready + all scores from champion; no auto-promote
- Production models / registry unchanged

## Offline vs online

| Mode | What it proves |
| --- | --- |
| Offline A/B | Quality comparison on labeled holdout; registry write only in demo workspace |
| Online A/B | Routing / weights / response `model_version` / per-group metrics under synthetic IDs |

## Airflow decision layer (Block 8.1)

Scope: **decision_layer_only** (no full retrain).
Evidence: `results/block8/airflow_trigger_decisions.json` — stable→skipped; drift→triggered; degradation→triggered; invalid→unavailable; `auto_promote=false`.

## Demo results (synthetic, no PII)

| Check | Result |
| --- | --- |
| Baseline data drift | `detected=false` |
| Controlled data drift | `detected=true`, share≈`0.375` |
| Concept/perf signal | `degradation_signal=true`, `confirmed_concept_drift=false` unless known synthetic C |
| Offline A/B | challenger comparison; **auto_promote=false** |

## Historical Stage 6 validation snapshot (2026-11-22)

Evidently `0.7.23` + pandas 2.2.x compatibility confirmed; full drift/A/B runtime evidence is in Block 8 (`results/block8/`) and this completion report.
