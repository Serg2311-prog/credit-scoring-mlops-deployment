# Матрица соответствия требованиям итогового проекта

**Актуализация:** 2026-11-26
**Источник требований:** задание курса (`ИТОГОВЫЙ ПРОЕКТ.docx`; локальный extract `results/block10/tz_extract.txt`, gitignored).
**Облачный статус:** [`results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md).
**Биллинг эксперимента (2026-11-26):** [`results/block11/FINAL_COST_REPORT.md`](../results/block11/FINAL_COST_REPORT.md).

### Легенда статусов

| Статус | Значение |
| --- | --- |
| `VERIFIED_LOCAL` | Локальный runtime/тест + evidence |
| `VERIFIED_CI` | Успешный GitHub Actions run |
| `VERIFIED_GPU` | GPU evidence (Colab T4 hardened) |
| `VERIFIED_CLOUD_INFRA` | Реальный Yandex Cloud infra (TF apply + cluster/node) |
| `IMPLEMENTED_NOT_EXECUTED` | Код/манифесты есть, целевой runtime не гонялся |
| `PARTIALLY_VERIFIED` | Часть требования подтверждена, есть задокументированный gap |
| `NOT_IMPLEMENTED` | Нет в репозитории |
| `OPTIONAL` | В задании помечено как опциональное |

Правило: `terraform validate` ≠ cloud deploy; unit test ≠ Docker E2E; synthetic ≠ production traffic.

---

## Сводка по этапам

| Этап | Обязательность | Статус доказательств |
| --- | --- | --- |
| Подготовка модели | обязательный | VERIFIED_LOCAL + VERIFIED_GPU (T4) |
| Cloud Infrastructure | обязательный | **VERIFIED_CLOUD_INFRA** (apply→destroy Block 11) + VERIFIED_LOCAL (validate); production apply NOT_EXECUTED |
| Контейнеризация и K8s | обязательный | VERIFIED_LOCAL (Compose/kind); cloud app ABORT; NP/HPA cloud runtime NOT_EXECUTED |
| CI/CD | обязательный | VERIFIED_CI (+ local CD demos) |
| Мониторинг | обязательный | VERIFIED_LOCAL (Block 8/8.1) |
| Мониторинг дрифта | обязательный | VERIFIED_LOCAL (Block 8/8.1) |
| Автоматизация (Airflow) | обязательный; scaling OPTIONAL | VERIFIED_LOCAL (Airflow E2E) |
| Документация | обязательный | VERIFIED_LOCAL |

---

## Этап 1 — Подготовка модели

| ID | Требование | Обяз. | Компонент | Путь | Проверка | Evidence | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.1 | NN на PyTorch | да | MLP train | `src/nn/` | `pytest`, train script | `docs/model_benchmark.md` | VERIFIED_LOCAL | — |
| 1.2 | ONNX conversion + parity | да | export/parity | `src/nn/export_onnx.py` | parity JSON | `results/block7/` | VERIFIED_LOCAL | — |
| 1.3 | Quantization | да | dynamic INT8 | `src/nn/quantize.py` | size/quality deltas | `docs/model_benchmark.md` | VERIFIED_LOCAL | не champion |
| 1.4 | CPU benchmark | да | batch probe | `scripts/block7_eval.py` | CPU JSON | `results/block7/` | VERIFIED_LOCAL | model_only ≠ HTTP |
| 1.5 | GPU benchmark | да | Colab T4 | `results/block7/colab/hardened/` | GPU JSON | `docs/gpu_benchmark_colab.md` | VERIFIED_GPU | INT8 GPU / GPU HTTP **не** выполнялись |
| 1.6 | API load | да | synthetic HTTP | `scripts/api_load_test.py` | summary JSON | `results/block7/api_load_summary.json` | VERIFIED_LOCAL | synthetic |
| 1.7 | Report | да | docs | `docs/model_benchmark.md` | review | тот же | VERIFIED_LOCAL | RF 0.7771 > MLP 0.7742 |

---

## Этап 2 — Cloud Infrastructure

| ID | Требование | Обяз. | Компонент | Путь | Проверка | Evidence | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2.1 | Terraform Yandex | да | modules/envs | `infra/terraform/` | `fmt`/`validate` + cloud apply→destroy | `results/block11/` | VERIFIED_CLOUD_INFRA | experiment applied then destroyed; staging/prod apply NOT_EXECUTED |
| 2.2 | VPC/K8s/Storage/Monitoring modules | да | modules | `infra/terraform/modules/*` | validate + live MK8s | stage2 + block11 | VERIFIED_CLOUD_INFRA | experiment minimal modules; YCR/storage optional off |
| 2.3 | Remote state | да | Object Storage | `backend*.example` + live | live then bucket deleted | `results/block11/` | VERIFIED_CLOUD_INFRA | locking NOT_VERIFIED; bucket destroyed after experiment |
| 2.4 | CPU/GPU node groups | да | k8s module | CPU live; GPU off | cloud worker Ready then destroy | block11 | PARTIALLY_VERIFIED | GPU group в облаке **не** запускалась |
| 2.5 | Security groups / NP | да | TF + K8s NP | modules + Calico | SG migration 12 rules; Calico live | block11 | PARTIALLY_VERIFIED | Calico CLOUD_INFRA; NP app enforcement CLOUD_APP ABORT |

---

## Этап 3 — Контейнеризация и K8s

| ID | Требование | Обяз. | Компонент | Путь | Проверка | Evidence | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3.1 | Multi-stage Docker | да | API/FE/models/dvc | `docker/Dockerfile.*` | compose build | `docs/docker_deployment.md` | VERIFIED_LOCAL | — |
| 3.2 | Compose API+frontend | да | compose | `docker-compose.yml` | smoke | stage3 report | VERIFIED_LOCAL | — |
| 3.3 | DVC in Docker | да | dvcdata image | `docker/Dockerfile.dvcdata` | build/repro | `dvc.yaml` | VERIFIED_LOCAL | не в runtime API |
| 3.4 | K8s Deployment/Service/Ingress | да | Kustomize | `k8s/` | kind E2E | `docs/kubernetes_local_deployment.md` | VERIFIED_LOCAL | cloud **app** deploy не выполнялось |
| 3.5 | ConfigMaps/Secrets | да | manifests | `k8s/base/` | apply local | stage3 | VERIFIED_LOCAL | examples only for secrets |
| 3.6 | Rolling update | да | strategy | overlays | manifests | k8s overlays | VERIFIED_LOCAL | — |

---

## Этап 4 — CI/CD

| ID | Требование | Обяз. | Компонент | Путь | Проверка | Evidence | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4.1 | Multi-stage GH Actions | да | workflows | `.github/workflows/` | Actions UI | `docs/cicd_pipeline.md` | VERIFIED_CI | — |
| 4.2 | Security scanning | да | Trivy | `ci-docker.yml` | CI | stage4 / IMAGE_BUILD | VERIFIED_CI | — |
| 4.3 | Staging/production CD | да | dry-run / promote digests | `cd-*.yml` | dry-run | cicd docs | PARTIALLY_VERIFIED | hosted cloud kube NOT_EXECUTED |
| 4.4 | Blue-Green / Canary / Istio | OPTIONAL | — | — | — | — | OPTIONAL | не реализовано |
| 4.5 | Rollback mechanism | OPTIONAL | digest promote fail-closed | scripts/ci | local demo | cicd docs | PARTIALLY_VERIFIED / OPTIONAL | не Istio |

---

## Этап 5 — Мониторинг

| ID | Требование | Обяз. | Компонент | Путь | Проверка | Evidence | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5.1 | Prometheus app+infra | да | scrape API+cAdvisor | `monitoring/prometheus/` | Block 8 E2E | `results/block8/` | VERIFIED_LOCAL | cAdvisor name labels Desktop **нет** |
| 5.2 | Grafana dashboards | да | provisioning | `monitoring/grafana/` | UI/API | block8 snapshots | VERIFIED_LOCAL | — |
| 5.3 | Loki / Alloy logs | да | stack | `monitoring/loki`, `alloy` | LogQL | block8 | VERIFIED_LOCAL | — |
| 5.4 | Log dashboard | OPTIONAL | Grafana | dashboards | provisioned | block8 | VERIFIED_LOCAL / OPTIONAL | — |
| 5.5 | Metric alerts | да | rules+AM | `alerts.yml` | firing/resolved | `metric_alert_*.json` | VERIFIED_LOCAL | — |
| 5.6 | Log alerts | да | Loki ruler | `loki/rules` | firing/resolved | `log_alert_*.json` | VERIFIED_LOCAL | probe вне prod API |
| 5.7 | Runbook | да | docs | `docs/stage5_runbook.md` | review | — | VERIFIED_LOCAL | — |

---

## Этап 6 — Мониторинг дрифта

| ID | Требование | Обяз. | Компонент | Путь | Проверка | Evidence | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6.1 | Evidently data drift | да | pipeline | `src/monitoring/data_drift.py` | pytest+demo | `results/block8/drift/` | VERIFIED_LOCAL | — |
| 6.2 | Concept / performance decay | да | signals + synthetic exp | `concept_drift*`, experiment | reports | `concept_drift_experiment.json` | VERIFIED_LOCAL | synthetic ≠ prod proof |
| 6.3 | Drift dashboards | OPTIONAL | Grafana ml_* | exporter+dashboard | PromQL | block8 prometheus JSON | VERIFIED_LOCAL / OPTIONAL | job filter required |
| 6.4 | Seldon Core | OPTIONAL | — | — | — | — | OPTIONAL | NOT_IMPLEMENTED |
| 6.5 | A/B testing | да | offline+online | `ab_*`, compose ab.e2e | HTTP E2E | `online_ab_evidence.json` | VERIFIED_LOCAL | quant challenger; synthetic |
| 6.6 | Shadow deployment | OPTIONAL | — | — | — | — | OPTIONAL | NOT_IMPLEMENTED |
| 6.7 | Model registry | да | registry JSON | `models/model_registry.json` | immutability tests | block8 registry JSON | VERIFIED_LOCAL | demo isolated |

---

## Этап 7 — Автоматизация

| ID | Требование | Обяз. | Компонент | Путь | Проверка | Evidence | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7.1 | Airflow DAG retrain | да | DAG | `airflow_home/dags/` | Docker E2E | `docs/stage7_airflow_e2e_report.md` | VERIFIED_LOCAL | local only |
| 7.2 | Triggers data/drift | да | triggers | `src/retraining/` | unit+E2E | stage7 + block8 decisions | VERIFIED_LOCAL | — |
| 7.3 | Auto test new models | OPTIONAL | eval tasks | retraining | E2E eval JSON | stage7 | VERIFIED_LOCAL / OPTIONAL | — |
| 7.4 | Cluster autoscaling / geo / Redis | OPTIONAL | — | — | — | — | OPTIONAL | NOT_IMPLEMENTED |
| 7.5 | No auto-promote | политика проекта | registry gate | code | tests | stage7 | VERIFIED_LOCAL | `auto_promote=false` |

---

## Документация

| ID | Требование | Обяз. | Компонент | Путь | Проверка | Evidence | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D.1 | README | да | entrypoint | `README.md` | review | — | VERIFIED_LOCAL | — |
| D.2 | Architecture docs | да | Mermaid | `docs/architecture/overview.md` | review | — | VERIFIED_LOCAL | — |
| D.3 | Runbooks / reports | да | stage docs | `docs/stage*_*.md` | review | — | VERIFIED_LOCAL | — |
| D.4 | Evidence index / defense | да | docs package | `docs/evidence_index.md`, `defense_guide.md`, `quick_review.md` | review | — | VERIFIED_LOCAL | — |

---

## Явные NOT_EXECUTED / OPTIONAL gaps

| Тема | Статус |
| --- | --- |
| `cloud-experiment` terraform apply + live remote state + MK8s worker | **VERIFIED_CLOUD_INFRA** then destroy verified (Block 11) |
| Cloud ML app deploy (GHCR / inference / HPA / NP+/−) | **не выполнялось** (local images only) |
| staging/production terraform apply | IMPLEMENTED_NOT_EXECUTED |
| GPU node group runtime | IMPLEMENTED_NOT_EXECUTED |
| Istio Blue-Green / Canary | OPTIONAL / NOT_IMPLEMENTED |
| Seldon / shadow | OPTIONAL / NOT_IMPLEMENTED |
| Redis / geo replication / cluster autoscaling | OPTIONAL / NOT_IMPLEMENTED |
| GPU INT8 + GPU HTTP load | NOT_IMPLEMENTED (не выполнялись) |
