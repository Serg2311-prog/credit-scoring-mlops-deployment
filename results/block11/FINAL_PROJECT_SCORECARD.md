# FINAL_PROJECT_SCORECARD — Block 11.14

**Source TZ:** `results/block10/tz_extract.txt` (from `ИТОГОВЫЙ ПРОЕКТ.docx`). Max **50**.
**Official score:** mentor only. Below is an independent evidence-based estimate.

## Comparison Block 10.2 → Block 11.14

| # | Criterion | Max | Block 10.2 | Block 11.14 | Rationale |
|---|-----------|----:|----------:|------------:|-----------|
| 1 | Подготовка модели | 5 | 5 | **5** | ONNX/parity/benchmarks unchanged; protected SHA MATCH; local smoke/parity PASS |
| 2 | Cloud Infrastructure | 7 | 7 | **7** | Already at max on validate/modularity/security; Block 11 adds live apply+destroy evidence — **no inflation beyond 7** |
| 3 | Docker и Kubernetes | 8 | 7 | **7** | Local Compose/kind strong; cloud app ABORT; HPA/NP enforcement still not runtime-proven (not a delivery Trivy issue — see below) |
| 4 | CI/CD | 5 | 5 | **5** | Gates intact; not weakened |
| 5 | Мониторинг | 8 | 8 | **8** | Local Block 8 evidence; cloud monitoring stack not claimed |
| 6 | Drift / model quality | 7 | 7 | **7** | Unchanged |
| 7 | Автоматизация | 5 | 5 | **5** | Airflow local E2E; optional scaling not required |
| 8 | Документация | 5 | 5 | **5** | Reconciled for Block 11 facts |
| | **TOTAL** | **50** | **49** | **49** | |

## Most likely / range

| Estimate | Score | Notes |
|----------|------:|-------|
| Confirmed minimum (strict) | **47–48** | If grader docks cloud-app absence + scaling/NP runtime only |
| Most likely | **49** | Same soft residual as Block 10.2 on scaling/NP runtime |
| Optimistic ceiling | **50** | If grader accepts static HPA + infra apply as full cloud story without app runtime |

## Why not raise score for cloud apply?

TZ Cloud criterion is **Terraform workability, modularity, security** (already scored 7/7). Creating then destroying MK8s strengthens evidence quality but does not unlock points above the criterion max. Unfinished cloud app and missing HPA/NP runtime proofs prevent claiming a free upgrade of criterion 3.

## Remaining limitations affecting grade risk

1. ABORT_CLOUD_APP — no cloud inference/HPA/NP/monitoring/rollback proof
2. Historical experiment API image (trixie) had 53 HIGH — **excluded from delivery**; `Dockerfile.api` restored to `main`; merge-prep Trivy gate **PASS** (not a current merge blocker; see `MERGE_READINESS_REPORT.md`)
3. kind NP enforcement still unproven
4. Optional items (Istio/Seldon/Redis) correctly **not** treated as mandatory

## Closure status

- Block 11.14 experiment closeout: `READY_WITH_DOCUMENTED_LIMITATIONS`
- Block 11.15 merge prep: `READY_FOR_FINAL_MERGE` / staging hygiene: see `MERGE_READINESS_REPORT.md`
