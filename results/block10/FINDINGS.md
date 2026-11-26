# FINDINGS — Block 10 Independent Audit

Severity: **P0** critical / **P1** mandatory criterion impact / **P2** quality / **P3** cosmetic.

Historical finding bodies below are **unchanged** from Block 10. Statuses updated through Block **10.2**.

| ID | Block 10.2 status |
| --- | --- |
| F-P1-01 | FIXED_AND_VERIFIED |
| F-P1-02 | ACCEPTED_LIMITATION (instructor pack prepared locally) |
| F-P1-03 | FIXED_AND_VERIFIED (`quant_roc_auc_proof_block102.json`) |
| F-P1-04 | FIXED_AND_VERIFIED |
| F-P2-01 | FIXED_AND_VERIFIED |
| F-P2-02 | FIXED_AND_VERIFIED (static HPA); runtime NOT_EXECUTED |
| F-P2-03 | ACCEPTED_LIMITATION |
| F-P2-04 | ACCEPTED_LIMITATION |
| F-P2-05 | ACCEPTED_LIMITATION |
| F-P2-06 | FIXED_AND_VERIFIED (+ obs runtime) |
| F-P2-07 | FIXED_AND_VERIFIED (+ obs runtime) |
| F-P2-08 | ACCEPTED_LIMITATION |
| F-P2-09 | ACCEPTED_LIMITATION |
| F-P3-01 | ACCEPTED_LIMITATION |
| F-P3-02 | ACCEPTED_LIMITATION |
| F-P3-03 | ACCEPTED_LIMITATION |
| F-P3-04 | FIXED_AND_VERIFIED |
| F-P3-05 | ACCEPTED_LIMITATION |

Also see `FINAL_ACCEPTANCE_REPORT.md`.

---

## P0 — Critical (submission blockers)

**None identified.**

---

## P1 — Substantial

### F-P1-01 — README quickstart omits runtime ML/API dependencies

| Field | Value |
| --- | --- |
| Description | Quickstart installs only `requirements-dev.txt` (pytest/httpx/flake8/black/dvc). CI installs `requirements.txt` + `requirements-api.txt` + `requirements-nn.txt`. Clean clone following README cannot import numpy/pandas/sklearn/fastapi. |
| Location | `README.md` L113–L115, L124–L126; `requirements-dev.txt` L1–L5 |
| Reproduce | Clean checkout `bdb8b43` → `pip install -r requirements-dev.txt` → `pytest -m "not k8s and not e2e"` → `ModuleNotFoundError: numpy` |
| Evidence | Clean clone `%TEMP%\cs-mlops-audit-bdb8b43`; CI Python workflow installs full set |
| Fix | Document `pip install -r requirements.txt -r requirements-dev.txt -r requirements-api.txt -r requirements-nn.txt` (match CI) |
| Effort | 15–30 min |
| Before submit? | **Recommended** (not strictly blocking if teacher uses CI as oracle) |

### F-P1-02 — Production model binaries absent from Git / clean clone

| Field | Value |
| --- | --- |
| Description | Tracked under `models/`: only `.gitkeep` + `model_registry.json`. ONNX/PT/preprocessor are local/gitignored and **not** DVC outs. Clean clone cannot run production-parity inference without external artifacts. Specialist ML audit treats “clone → serve production ONNX” as hard fail for that criterion; for academic submission this remains **P1** (synthetic CI path + instructor pack mitigate), not a TZ submission P0. |
| Location | `models/` tracked listing; `.gitignore`; `dvc.yaml`; clone inventory |
| Reproduce | `git archive` / clean clone → `Test-Path models/credit_scoring_nn.onnx` → False |
| Evidence | Clone HEAD files; SHA256 of local production artifacts recorded in `audit_baseline.json`; cross-check ML audit |
| Fix | Release asset / encrypted instructor package / documented DVC remote with read-only token; keep SHA256SUMS in repo |
| Effort | 2–4 h |
| Before submit? | **Provide instructor package separately**; do not silently copy into Git without policy review |

### F-P1-03 — Quantized holdout ROC-AUC inconsistent across docs/JSON

| Field | Value |
| --- | --- |
| Description | Experimental INT8 quality is documented as both **0.7720** and **0.7736** with different confusion matrices (TN/FP 3630/1043 vs 3622/1051). Not rounding noise. FP32 ~0.7742 and flip rate ~2.18% are stable; champion selection unaffected. |
| Location | `docs/model_benchmark.md` §5 vs §6.1; `artifacts/onnx_quantization.json` / quality JSON vs `artifacts/benchmark_cpu.json`; `docs/final_project_report.md` L46; `docs/defense_guide.md` |
| Reproduce | Diff quoted quant ROC-AUC and confusion cells across those files |
| Evidence | ML audit |
| Fix | Pick one canonical quant eval artifact; regenerate conflicting tables from it |
| Effort | 1–2 h |
| Before submit? | **Recommended** before defense Q&A on metrics |

### F-P1-04 — Primary CI workflows omit explicit `permissions:`

| Field | Value |
| --- | --- |
| Description | `ci-python`, `ci-docker`, `ci-kubernetes`, `ci-infrastructure`, `ci-airflow-dag`, `release-candidate` inherit repo default GITHUB_TOKEN scope. CD/orchestrator workflows do set least-privilege `permissions:`. |
| Location | `.github/workflows/ci-*.yml` (no top-level `permissions:`); contrast `cd-staging.yml` / `ci-cd.yml` |
| Reproduce | Open workflow YAML; search `^permissions:` |
| Evidence | Infra/CI audit |
| Fix | Add `permissions: contents: read` (and minimal extras) to each CI workflow |
| Effort | 30–60 min |
| Before submit? | Recommended |

---

## P2 — Quality / consistency

### F-P2-01 — Stale Baseline commit in README header

| Field | Value |
| --- | --- |
| Description | README table shows Baseline `0df191a`; actual HEAD/origin is `bdb8b43`. |
| Location | `README.md` L9 |
| Fix | Update to `bdb8b43` |
| Effort | 5 min |
| Before submit? | Recommended |

### F-P2-02 — No HorizontalPodAutoscaler

| Field | Value |
| --- | --- |
| Description | Scaling via fixed replicas + rollingUpdate; no HPA. Cluster autoscaling marked OPTIONAL/NOT_IMPLEMENTED in requirements matrix. |
| Location | `k8s/overlays/production/patch-resources.yaml` (`replicas: 2`); matrix row 7.4 |
| Fix | Optional HPA manifest for API Deployment |
| Effort | 1–2 h |
| Before submit? | Optional |

### F-P2-03 — NetworkPolicy enforcement not runtime-proven on kind

| Field | Value |
| --- | --- |
| Description | Manifests present; kindnet enforcement explicitly undocumented as unproven. |
| Location | `k8s/` NetworkPolicy resources; `README.md` L176 |
| Fix | Calico/Cilium demo or cloud CNI evidence |
| Effort | 2–6 h |
| Before submit? | No (honest disclosure sufficient) |

### F-P2-04 — Absolute / personal path strings in tracked scripts

| Field | Value |
| --- | --- |
| Description | Pattern matches for personal path substrings in 2 tracked files (sanitizer / stage script). Not credentials. |
| Location | `scripts/block8/sanitize_block8_evidence.py`; `scripts/run_stage1.ps1` |
| Fix | Keep path patterns generic; ensure no live personal absolute paths in defaults |
| Effort | 30–60 min |
| Before submit? | Optional |

### F-P2-05 — Terraform / cloud apply never executed

| Field | Value |
| --- | --- |
| Description | Honest: no Yandex Cloud production. Static validation EXECUTED_PASS. Remote state/locking example-only (`backend.tf.example`). |
| Location | README L10–L11; `infra/terraform/` |
| Fix | Optional sandboxed apply with destroyed resources + evidence |
| Effort | High |
| Before submit? | Not required by optional marking / honesty |

### F-P2-06 — API registers unset drift gauges → Prometheus default 0

| Field | Value |
| --- | --- |
| Description | API process exposes `ml_data_drift_*` gauges that stay at 0 unless scraped from `drift-metrics-exporter`. Unfiltered PromQL can look like “no drift”. Grafana model-quality dashboard filters `job="drift-metrics-exporter"`. Exporter itself fail-closes with 503 (does not invent zeros). |
| Location | `src/api/metrics.py`; `monitoring/grafana/dashboards/model_quality_drift.json`; `results/block8/prometheus_ml_metrics_by_job.json` |
| Evidence | Monitoring audit |
| Fix | Do not register unset gauges on API, or document required job filter in runbook more prominently |
| Effort | 1–2 h |
| Before submit? | Optional (disclose on defense) |

### F-P2-07 — Drift metrics exporter only on observability E2E overlay

| Field | Value |
| --- | --- |
| Description | Base `docker-compose.observability.yml` / `prometheus.yml` do not scrape exporter; continuous drift panels need `docker-compose.observability.e2e.yml`. |
| Location | `docker-compose.observability.e2e.yml`; `monitoring/prometheus/prometheus.e2e.yml` vs `prometheus.yml` |
| Evidence | Monitoring audit |
| Fix | Optional scrape job in base prometheus for local demos |
| Effort | 1 h |
| Before submit? | Optional |

### F-P2-08 — NetworkPolicy Ingress-only; TF worker NAT / open egress

| Field | Value |
| --- | --- |
| Description | K8s NP `policyTypes: [Ingress]` only (no egress deny). Terraform node templates use `nat = true`; SG egress 0.0.0.0/0 noted as harden-later. |
| Location | `k8s/base/networkpolicy.yaml`; `infra/terraform/modules/kubernetes/main.tf`; `modules/network/main.tf` |
| Evidence | Infra/CI audit |
| Fix | Egress NetworkPolicy + tighten SG/NAT if cloud apply ever runs |
| Effort | 2–4 h |
| Before submit? | Optional (cloud NOT_EXECUTED) |

### F-P2-09 — RF baseline historical; early-stop does not checkpoint best weights

| Field | Value |
| --- | --- |
| Description | RF metrics imported from prior project JSON (not re-trained in-repo). MLP early-stop tracks best epoch then scratch-retrains that many epochs on full train (anti-leakage) — final weights ≠ exact best-val checkpoint. |
| Location | `artifacts/baseline_metrics.json`; `src/nn/train_nn.py` early-stop/retrain loop |
| Evidence | ML audit |
| Fix | Optional same-pipeline RF re-run; optional best-state_dict export for research reproducibility |
| Effort | 2–6 h |
| Before submit? | No |

---

## P3 — Cosmetic / local-only

### F-P3-01 — Local Airflow demo default password

| Field | Value |
| --- | --- |
| Description | Entrypoint defaults local web user password to `admin` when env unset. File comments “NOT production”. |
| Location | `scripts/airflow/entrypoint.sh` L16–L17 |
| Fix | Require env var without default in any shared environment |
| Effort | 15 min |

### F-P3-02 — Node.js 20 / tar cache CI warnings

| Field | Value |
| --- | --- |
| Description | Common GHA deprecation noise; runs still SUCCESS. |
| Criticality | Low |
| Fix | Bump actions when convenient |

### F-P3-03 — Dense / templated documentation phrasing

| Field | Value |
| --- | --- |
| Description | Some sections use repetitive verification tables; not proof of AI authorship. Overall honesty about limitations is strong. |
| Examples | Evidence index tables; repeated `VERIFIED_*` taxonomies |

### F-P3-04 — Dead `ENABLE_E2E_LOG_PROBE` env in AB overlay

| Field | Value |
| --- | --- |
| Description | Compose sets env flag ignored by Settings (`extra=ignore`). Probe remains absent from prod API. |
| Location | `docker-compose.ab.e2e.yml`; `src/api/settings.py` |
| Evidence | Monitoring audit |

### F-P3-05 — API/models base images not digest-pinned; Airflow outside Trivy matrix

| Field | Value |
| --- | --- |
| Description | Frontend/dvc digest-pinned; API/models use floating tags. Airflow image not in `ci-docker` Trivy matrix. |
| Location | `docker/Dockerfile.api`, `Dockerfile.models`; `.github/workflows/ci-docker.yml` |
| Evidence | Infra/CI audit |

---

## Specialist cross-checks (post-report)

| Specialist | ID | Delta absorbed |
| --- | --- | --- |
| ML correctness | ML audit | F-P1-02 nuance, F-P1-03, F-P2-09 |
| Infra / Docker / TF / GHA | Infra/CI audit | F-P1-04, F-P2-08, F-P3-05 |
| Monitoring / Drift / AB / Airflow | Monitoring audit | F-P2-06, F-P2-07, F-P3-04; Block8 **46/46** key files present |


---

## Non-findings (explicitly checked, OK)

- No AWS keys / PEM private keys in tracked text files (456 files scanned).
- `auto_promote=false` enforced in API/AB/retraining paths.
- Production registry write blocked without `allow_production_write`.
- No e2e log probe endpoint in production API source.
- Drift exporter fail-closed (503; does not invent zeros).
- Protected model SHA256 unchanged during audit.
- Block7/Block8 git trees unchanged (`9a7dab26…` / `fdb12d7a…`).
- Five CI workflows SUCCESS on `bdb8b43`.
- PyTorch↔ONNX FP32 parity PASS (max \|Δp\| ≈ 7e-8).
- Optional components absent → **no score penalty** per TZ footnote.
