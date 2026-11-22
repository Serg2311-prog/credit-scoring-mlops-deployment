# Stage 6 Validation Report

**Date:** 2026-11-22
**Environment:** Windows 11, PowerShell 5.1, Python 3.13, venv, 8 GB RAM, no GPU
**Docker Desktop:** not used for this stage

## Dependency compatibility

| Package | Pin / constraint | Result |
| --- | --- | --- |
| `evidently` | `==0.7.23` | PASS (import + DataDriftPreset) |
| `pandas` | `>=2.2.3,<3` (installed `2.2.3`) | PASS — required; pandas 3.x broke Evidently |
| `numpy` | `2.5.5` (existing) | PASS with Evidently 0.7.x |

Notes: Evidently `0.4.40` needs `numpy<2.1` (no py313 wheels). Evidence API used: `evidently.Report` + `DataDriftPreset` (v0.7).

## Checks executed

| Check | Command | Result |
| --- | --- | --- |
| Stage 6 unit tests | `pytest tests/monitoring -q` | **PASS** 18 |
| Full suite | `pytest -q` | **PASS** 115 |
| Format | `black --check` (stage 6 touched files) | **PASS** |
| Lint | `flake8` (stage 6 touched files) | **PASS** |
| Whitespace | `git diff --check` | **PASS** (CRLF warnings only) |
| Demo | `python -m src.monitoring.cli demo` | **PASS** → `artifacts/monitoring/demo_summary.json` |

## Demo outcomes (synthetic only)

| Artifact | Key fields |
| --- | --- |
| Data drift (shift) | `data_drift_detected=true`, `drift_share=0.375`, target excluded |
| Concept signal | `degradation_signal=true`, `confirmed_concept_drift=false` |
| Offline A/B | `challenger_favored=true`, `auto_promote=false`, ΔROC-AUC ≈ `0.103` |

No real credit/PII rows were written to Git.

## Stages 1–5 regression

Full `pytest` includes API, NN, k8s manifest, terraform structure, CI workflow tests — **115 passed**. No intentional API contract break; A/B defaults to **disabled**.

## Remaining / out of scope

- Live dual-ONNX A/B in production requires providing `CHALLENGER_MODEL_PATH` and explicit `AB_ENABLED=true`.
- Prometheus scrape of `ml_*` quality gauges still needs offline jobs to call `update_*` helpers (gauges are registered; values update when helpers run).
- Airflow orchestration of these checks → Stage 7.
- Cloud deploy / auto-promote → intentionally not implemented.
