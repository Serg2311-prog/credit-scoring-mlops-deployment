# FINAL SCORECARD — Block 10 / 10.1 / 10.2

## Timeline of scores (do not conflate)

| Moment | Commit / tree | Score (most likely) | Status |
| --- | --- | ---: | --- |
| Block 10 audit | baseline `bdb8b43` (pre-remediation) | **48 / 50** | READY_WITH_MINOR_LIMITATIONS |
| Block 10.1 remediation | local uncommitted fixes | **50 / 50** (proposed) | READY_FOR_SUBMISSION (pending verify) |
| **Block 10.2 acceptance** | same remediations + verification | **49 / 50** most likely | **READY_FOR_SUBMISSION** |

Block 10.2 does **not** auto-confirm 50/50. After runtime/clean-clone checks, one soft residual remains on the K8s scaling criterion (HPA configured, Metrics Server / kind runtime **NOT_EXECUTED**). Independent most-likely score: **49**. Confirmed minimum: **48**. Maximum defensible without live cloud: **50**.

## Block 10.2 scores (post-verification)

| # | Criterion (TZ) | Max | Score | Notes |
| ---: | --- | ---: | ---: | --- |
| 1 | Подготовка модели | 5 | **5** | Quant proof JSON; FP32 champion unchanged |
| 2 | Cloud Infrastructure | 7 | **7** | Validate/tests; apply NOT_EXECUTED (honest) |
| 3 | Docker и Kubernetes | 8 | **7** | Strong images/manifests/HPA **static**; HPA runtime + NP enforcement unproven |
| 4 | CI/CD | 5 | **5** | Permissions + gates |
| 5 | Мониторинг | 8 | **8** | Obs runtime: exporter scrape OK; no API fake zeros |
| 6 | Drift | 7 | **7** | Status model + Evidently |
| 7 | Автоматизация | 5 | **5** | Airflow unchanged |
| 8 | Документация | 5 | **5** | README deps, instructor pack doc, metric consistency |
| | **TOTAL** | **50** | **49** | |

### Why not automatic 50?

HPA is correctly declared (`autoscaling/v2`, CPU 70%, min 2 / max 6) and kustomize-renders, but Block 10.2 did **not** run Metrics Server / kind autoscaling. A strict reading of «настройка масштабирования» can still withhold 1 point without runtime proof. Cloud apply remains NOT_EXECUTED but is not deducted when IaC workability is accepted via validate/tests.

## Conditions for 50/50

- Kind (or cloud) demo: Metrics Server + HPA scales under load, **or** grader accepts static HPA as sufficient; **and**
- Instructor model pack used for production inference parity on review.
