# Stage 6 Runbook — Data Drift, Quality Signals, A/B

## Scope

Stage 6 adds **offline** monitoring for:

1. **Data drift** — feature distribution change (Evidently `0.7.23`).
2. **Quality / concept-drift signal** — labeled metric degradation vs a reference window.
3. **A/B** — deterministic routing + offline same-holdout champion/challenger compare.

No automatic production model promotion. No new always-on heavy containers.

## Architecture

```
reference CSV ─┐
current CSV ───┼─► src.monitoring.data_drift (Evidently) ─► artifacts/monitoring/data_drift/
               │
labeled y/p ───┼─► src.monitoring.concept_drift ───────────► artifacts/monitoring/concept_drift/
               │
same holdout ──┼─► src.monitoring.ab_testing ──────────────► artifacts/monitoring/ab_testing/
               │
API (optional) ┴─► AB_ENABLED routing + ml_* Prometheus gauges (stage 5 stack)
```

| Check | What it means | What it does **not** mean |
| --- | --- | --- |
| Data drift | Features shifted vs reference | Model quality dropped / concept changed |
| Degradation signal | ≥N metrics dropped past thresholds | Confirmed concept drift |
| Offline A/B | Same labeled rows, two score columns | Safe auto-cutover |

## Thresholds

Config: `configs/monitoring/stage6_thresholds.yaml`

| Block | Key defaults |
| --- | --- |
| `data_drift.share_threshold` | `0.3` (share of drifted features) |
| `data_drift.min_rows` | `30` |
| `concept_drift.require_metric_drops` | `2` (ROC-AUC / PR-AUC / F1) |
| `concept_drift.roc_auc_drop` / `pr_auc_drop` / `f1_drop` | `0.03` / `0.03` / `0.05` |
| `ab_testing.traffic_challenger_share` | `0.2` |
| `ab_testing.hash_salt` | `credit-scoring-ab-v1` |

## Commands (Windows PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:OMP_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"

# Synthetic demo (no real credit/PII data)
.\.venv\Scripts\python.exe -m src.monitoring.cli demo

# Data drift
.\.venv\Scripts\python.exe -m src.monitoring.cli data-drift `
  --reference path\ref.csv --current path\cur.csv --target "default.payment.next.month"

# Quality degradation signal (needs y + proba columns)
.\.venv\Scripts\python.exe -m src.monitoring.cli concept-drift `
  --reference path\ref_scored.csv --current path\cur_scored.csv `
  --y-column y --proba-column proba

# Offline A/B on the SAME holdout
.\.venv\Scripts\python.exe -m src.monitoring.cli ab-offline `
  --data path\holdout_scored.csv `
  --y-column y --champion-proba champion_proba --challenger-proba challenger_proba
```

Outputs land under `artifacts/monitoring/` (gitignored). Model registry: `models/model_registry.json`.

## Prometheus metrics (stage 5 stack)

Exported on API `/metrics` (same registry as stage 5):

| Metric | Type | Labels |
| --- | --- | --- |
| `ml_data_drift_share` | Gauge | **exporter-metrics-exporter only** (not API) |
| `ml_data_drift_detected` | Gauge | **exporter-metrics-exporter only** |
| `ml_monitoring_artifact_status` | Gauge | 0 unavailable / 1 valid / 2 stale / 3 invalid |
| `ml_model_roc_auc` | Gauge | `model_role` |
| `ml_model_pr_auc` | Gauge | `model_role` |
| `ml_model_f1` | Gauge | `model_role` |
| `ml_ab_experiment_samples` | Counter | `ab_group`=`champion\|challenger` |

API live helper: `src.api.metrics.observe_ab_sample`. Offline drift/quality: `scripts/block8/drift_metrics_exporter.py` + `src.monitoring.prometheus_export`.

## API A/B (optional)

Disabled by default (`AB_ENABLED=false`). When enabled:

- Hash routing via `AB_HASH_SALT` + `AB_CHALLENGER_SHARE`.
- Optional second ONNX: `CHALLENGER_MODEL_PATH` + `CHALLENGER_MODEL_VERSION`.
- If challenger file is missing, scores stay on champion; groups are still recorded.
- **No auto-promote.** Rollback: set `AB_ENABLED=false`, point `MODEL_*` to champion, restart.

## Interpreting results

1. **Data drift detected** → investigate pipeline / population shift; run quality check if labels exist.
2. **`degradation_signal=true`** → review; do **not** claim confirmed concept drift from one metric.
3. **`challenger_statistically_favored=true`** → human gate only; keep champion until confirmed.

## Constraints

- Python 3.13 + Evidently `0.7.23` requires **pandas 2.2.x** (`pandas>=2.2.3,<3`).
- Use synthetic or anonymized extracts in Git; never commit real client credit rows.
- HTML Evidently reports can be multi‑MB; prefer `--no-html` in CI/tests.
- Online A/B group quality is confounded by sample mix → prefer offline same-holdout compare.
