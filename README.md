# credit-scoring-mlops-deployment

Промышленное развёртывание кредитной скоринговой системы с полным MLOps-циклом (учебный итоговый проект).

**Цель:** воспроизводимый конвейер от обучения и ONNX-serving до IaC, CI/CD, observability, мониторинга дрейфа/A/B и Airflow-retraining — без фиктивных метрик и без неподтверждённого cloud production.

**Статус:** этапы **0–7 реализованы в репозитории**.

Подтверждённый коммит этапа 7: [`65de3ad`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/commit/65de3ad680a2fc7f3fcbe374aeb07f485d773b63).

Cloud `terraform apply` **не выполнялся**. Production в Yandex Cloud **не развёрнут**. Airflow Docker E2E — **VERIFIED_LOCAL** (см. `docs/stage7_airflow_e2e_report.md`); **VERIFIED_CI** для compose E2E не заявляется.

Исходный ML-проект: [credit-default-prediction](https://github.com/Serg2311-prog/credit-default-prediction).

---

## Архитектура и технологии

Краткий контур системы:

```text
UCI raw CSV
  → prepare / validate (Pandera)
  → FE + preprocessor
  → MLP (PyTorch) → ONNX FP32 API
  → Docker / kind (локально) + Terraform (IaC без apply)
  → GitHub Actions CI/CD
  → Prometheus / Grafana / Loki / Alloy / Alertmanager
  → Evidently data drift + quality signals + A/B
  → Airflow-ready retraining (candidate only, без auto-promote)
```

| Слой | Технологии |
| --- | --- |
| ML | PyTorch MLP, scikit-learn preprocessing, ONNX Runtime |
| Serving | FastAPI, Prometheus metrics, JSON logging |
| Containers / K8s | Docker Compose, kind, Kustomize |
| IaC | Terraform (Yandex Cloud modules), validate/fmt only |
| CI/CD | GitHub Actions, Trivy, kubeconform |
| Observability | Prometheus, Grafana, Loki, Alloy, Alertmanager |
| Monitoring | Evidently 0.7.23, PSI enrichment, A/B routing helpers |
| Retraining | `src/retraining`, Airflow 2.9.3 DAG (Linux container) |

**Baseline (immutable без реального переобучения):**

| Модель | Test ROC-AUC | Источник |
| --- | --- | --- |
| RandomForest (исходный baseline) | **0.7771** | [`artifacts/baseline_metrics.json`](artifacts/baseline_metrics.json) |
| MLP / ONNX FP32 | **0.7742** | [`docs/model_benchmark.md`](docs/model_benchmark.md) |

---

## Этап 0 — подготовка проекта и baseline

### Цель

Зафиксировать аудит исходного репозитория, архитектуру целевой системы, матрицу требований и неизменяемый RF-baseline.

### Реализованные компоненты

- План реализации и карта reuse/adapt/drop
- Матрица требований по этапам
- Архитектурный обзор
- Исторические метрики RF в `artifacts/baseline_metrics.json`

### Проверка

- Наличие документов этапа 0 и baseline JSON в репозитории
- Baseline ROC-AUC **0.7771** соответствует `artifacts/baseline_metrics.json`

### Документация

- [docs/implementation_plan.md](docs/implementation_plan.md)
- [docs/requirements_matrix.md](docs/requirements_matrix.md)
- [docs/architecture/overview.md](docs/architecture/overview.md)

---

## Этап 1 — ML, PyTorch, ONNX, квантование и benchmark

### Цель

Обучить совместимую MLP на той же схеме признаков UCI, экспортировать в ONNX, сравнить с RF-baseline честным benchmark.

### Реализованные компоненты

- Обучение MLP (`src/nn/train_nn.py`), val только из train
- Экспорт ONNX FP32 и dynamic quantization
- Parity PyTorch ↔ ONNX, CPU benchmark (несколько batch size)
- GPU benchmark как отдельный сценарий (auto-skip без GPU)

### Проверка

- Локальные unit/integration-тесты модели и экспорта
- Зафиксированные метрики: MLP/ONNX FP32 test ROC-AUC **0.7742**
- Отчёт: [docs/model_benchmark.md](docs/model_benchmark.md), [docs/stage1_audit_report.md](docs/stage1_audit_report.md)

### Документация

- [docs/model_benchmark.md](docs/model_benchmark.md)
- [docs/stage1_audit_report.md](docs/stage1_audit_report.md)
- Скрипт: `scripts/run_stage1.ps1`

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
.\scripts\run_stage1.ps1
```

---

## Этап 2 — Infrastructure as Code, Terraform, Yandex Cloud

### Цель

Подготовить воспроизводимый IaC для staging/production в Yandex Cloud **без обязательного apply**.

### Реализованные компоненты

- Модули Terraform: network, iam, kubernetes, registry, kubernetes, monitoring
- Окружения `infra/terraform/environments/staging` и `production`
- Примеры backend/tfvars без секретов в Git
- Оценка стоимости в документации

### Проверка

- `terraform fmt -recursive -check`
- `terraform init -backend=false` + `validate` (без cloud credentials)
- **`terraform apply` не выполнялся**

### Документация

- [docs/terraform_infrastructure.md](docs/terraform_infrastructure.md)
- [docs/stage3b_validation_report.md](docs/stage3b_validation_report.md)
- [infra/terraform/README.md](infra/terraform/README.md)
- [docs/cloud_cost_estimate.md](docs/cloud_cost_estimate.md)

```powershell
terraform -chdir=infra/terraform fmt -recursive -check
terraform -chdir=infra/terraform/environments/staging init -backend=false
terraform -chdir=infra/terraform/environments/staging validate
```

---

## Этап 3 — Docker, Kubernetes, DVC

### Цель

Упаковать inference в CPU Docker-образы (API + frontend), Ingress/NetworkPolicy и воспроизводимый DVC pipeline для demo-данных.

### Реализованные компоненты

- Multi-stage `docker/Dockerfile.api`, `Dockerfile.models`, `Dockerfile.frontend`, `Dockerfile.dvcdata`
- Compose: API `:8000` + frontend UI `:8081` (nginx proxy `/api` → backend)
- Kustomize: Deployment/Service frontend+API, Ingress, NetworkPolicy
- kind config с port-mapping под ingress-nginx (пересоздание кластера нужно для host `:8080`)

### DVC

Рабочий pipeline: `dvc.yaml` / `dvc.lock`, local remote `.dvc_remote/` (gitignored).
Stages: generate → prepare → validate_ml_ready (smoke train **без** записи production models).
DVC-in-Docker: отдельный образ `Dockerfile.dvcdata` (repro/push/pull); **не** раздувает API runtime.

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:Path = "$(Resolve-Path .\.venv\Scripts);$env:Path"
python -m dvc repro
python -m dvc push
docker build -f docker/Dockerfile.dvcdata -t credit-scoring-dvc-data:local .
```

### Проверка

- Compose UI+API smoke; Ingress E2E через `kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller`
- NetworkPolicy: манифесты verified; enforcement на kindnet = **не подтверждён**
- Отчёт: [docs/stage3_completion_report.md](docs/stage3_completion_report.md)

### Документация

- [docs/api_contract.md](docs/api_contract.md)
- [docs/docker_deployment.md](docs/docker_deployment.md)
- [docs/kubernetes_local_deployment.md](docs/kubernetes_local_deployment.md)
- [docs/stage3_completion_report.md](docs/stage3_completion_report.md)
- [k8s/README.md](k8s/README.md)

```powershell
docker compose up -d --build
# UI http://127.0.0.1:8081
```

```powershell
.\scripts\k8s_ingress_e2e.ps1
.\scripts\k8s_networkpolicy_verify.ps1
```

---

## Этап 4 — CI/CD, GitHub Actions, security scanning

### Цель

Автоматизировать quality gates, сборку образов, security scanning и offline-проверки IaC/K8s на GitHub-hosted runners.

### Реализованные компоненты

- Workflows: CI Python, CI Docker (+ Trivy), CI Infrastructure, CI Kubernetes
- Orchestrator `ci-cd.yml` (gate **5** CI → modes validation/publish/deploy; opt-in auto via `AUTO_STAGING_ENABLED`; GHCR SHA+digest; `staging-release.json`)
- `cd-production.yml` (promote digests **only** from verified staging run; Environment `production`)
- Kustomize overlays: `staging`, `production`, kind CD demos
- Release Candidate и CD Staging dry-run
- Локальные скрипты `scripts/ci/` (+ `local_cd_verify.ps1`, `staging_release_manifest.py`)
- Synthetic artifacts для CI без реальных кредитных PII в Git

### Проверка

На коммите [`65de3ad`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/commit/65de3ad680a2fc7f3fcbe374aeb07f485d773b63) успешно завершились **пять** GitHub Actions:

| Workflow | Результат | Run |
| --- | --- | --- |
| CI Python | SUCCESS | [45031957962](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45031957962) |
| CI Docker | SUCCESS | [45031957995](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45031957995) |
| CI Infrastructure | SUCCESS | [45031958107](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45031958107) |
| CI Kubernetes | SUCCESS | [45031957937](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45031957937) |
| CI Airflow DAG | SUCCESS | [45031958040](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45031958040) |

Ранее на этапе 4 также подтверждались kind E2E, Release Candidate и CD Staging dry-run (см. отчёт этапа 4) — это **не** означает cloud production deploy.

Block 5 / 5.1: локальный kind CD (staging→prod-demo→negative→recover) — **VERIFIED_LOCAL**; gate/provenance/fail-closed — **VERIFIED_STATIC**; GHCR push / cloud kube / hosted orchestrator — **NOT_EXECUTED** без commit/push и credentials.

### Документация

- [docs/cicd_pipeline.md](docs/cicd_pipeline.md)
- [docs/stage4_cicd_completion_report.md](docs/stage4_cicd_completion_report.md)
- [docs/stage4_validation_report.md](docs/stage4_validation_report.md)
- Workflows: `.github/workflows/`

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
.\scripts\ci\check.ps1
# optional kind CD demo (isolated namespaces):
# powershell -File scripts/ci/local_cd_verify.ps1
```

---

## Этап 5 — Observability: Prometheus, Grafana, Loki, Alloy, Alertmanager

### Цель

Локальный observability-стек для latency, ошибок, readiness и централизованных логов API.

### Реализованные компоненты

- `docker-compose.observability.yml`
- Конфигурации Prometheus / Grafana / Loki / Alloy / Alertmanager в `monitoring/`
- Метрики API (`credit_scoring_*`), structured JSON logs
- Runbook типовых инцидентов

### Проверка

- Локальный подъём стека и скрипты `scripts/observability/`
- Отчёт: [docs/stage5_validation_report.md](docs/stage5_validation_report.md)

### Документация

- [docs/stage5_runbook.md](docs/stage5_runbook.md)
- [docs/stage5_validation_report.md](docs/stage5_validation_report.md)
- [docs/architecture/observability.md](docs/architecture/observability.md)

```powershell
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
.\scripts\observability\check.ps1
```

| UI | URL |
| --- | --- |
| Grafana | http://127.0.0.1:3000 |
| Prometheus | http://127.0.0.1:9090 |
| Alertmanager | http://127.0.0.1:9093 |
| API `/metrics` | http://127.0.0.1:8000/metrics |

---

## Этап 6 — Monitoring: Data Drift, quality signals, A/B testing

### Цель

Offline-мониторинг сдвига распределений признаков, сигналов ухудшения качества на размеченных данных и сравнения Champion/Challenger.

### Реализованные компоненты

- Evidently `0.7.23` data drift (target исключается из признаков)
- Quality / concept-drift **signal** (не auto-proof concept drift)
- A/B hash-routing + offline same-holdout compare
- Метрики `ml_*` в Prometheus registry API
- CLI: `python -m src.monitoring.cli`
- Реестр версий: `models/model_registry.json`

### Проверка

- Unit-тесты `tests/monitoring/`
- Demo CLI без реальных кредитных PII в Git
- Пороги: `configs/monitoring/stage6_thresholds.yaml`

### Документация

- [docs/stage6_runbook.md](docs/stage6_runbook.md)
- [docs/stage6_validation_report.md](docs/stage6_validation_report.md)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:OMP_NUM_THREADS = "1"
.\.venv\Scripts\python.exe -m src.monitoring.cli demo
```

---

## Этап 7 — Airflow Retraining: DAG, триггеры, candidate training, evaluation, registry

### Цель

Воспроизводимый конвейер переобучения кандидата под Airflow с безопасной регистрацией и **без автоматического продвижения** production-модели.

### Реализованные компоненты

- Движок `src/retraining/` (validate → triggers → prepare → train → evaluate → register → report)
- Триггеры: `scheduled`, `new_data` (fingerprint), `data_drift`, `quality_drop`
- Same-holdout champion scoring (ONNX + preprocessor) или явный `needs_review`
- Candidate training в отдельный run-dir (production artifacts не перезаписываются)
- Atomic update `models/model_registry.json` без смены `production_champion`
- DAG: `airflow_home/dags/credit_scoring_retraining.py` (`max_active_runs=1`)
- Compose: `docker-compose.airflow.yml` (cron `0 3 * * 1`) + E2E overlay `docker-compose.airflow.e2e.yml` (`RETRAIN_SCHEDULE=None`)
- CLI: `python -m src.retraining.cli` (`baseline-input-state`, `check-triggers`, …)
- CI parse job: `.github/workflows/ci-airflow-dag.yml`

### Отсутствие automatic promotion

- `auto_promote` всегда `false`
- Dry-run не пишет в production registry
- Решение `accepted` / `needs_review` требует **ручного** cutover (MODEL_PATH / MODEL_VERSION / registry)
- Airflow-задача approval «вечного ожидания» не используется

### Проверка

- Локальные тесты и CLI dry-run/demo (без установки Airflow в Windows venv)
- Workflow **CI Airflow DAG** (parse) — SUCCESS на GitHub Actions
- Локальный Docker Airflow E2E — **VERIFIED_LOCAL** (`scripts/airflow/e2e_docker.ps1`: A/A2/B/C/D/E + scheduler `scheduled__*` proof)
- Отчёт: [docs/stage7_airflow_e2e_report.md](docs/stage7_airflow_e2e_report.md)

### Документация

- [docs/stage7_runbook.md](docs/stage7_runbook.md)
- [docs/stage7_airflow_e2e_report.md](docs/stage7_airflow_e2e_report.md)
- [docs/stage7_validation_report.md](docs/stage7_validation_report.md)
- Конфиг: `configs/retraining/stage7.yaml`

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:OMP_NUM_THREADS = "1"
.\.venv\Scripts\python.exe -m src.retraining.cli demo
.\.venv\Scripts\python.exe -m src.retraining.cli dry-run --input path\to\data.csv --modes scheduled
```

```powershell
# Staff (cron on) / E2E (schedule off) — ресурсоёмко; см. stage7_runbook.md
# docker compose -f docker-compose.airflow.yml up --build
# powershell -File scripts/airflow/e2e_docker.ps1
```

---

## Результаты тестирования и CI

### Локально (Windows, этап 7)

| Проверка | Результат |
| --- | --- |
| Полный `pytest` | **137 passed, 1 skipped** |
| `black --check` / `flake8` (затронутые пути этапа 7) | PASS |
| CLI retraining demo | PASS (`auto_promote=false`) |

Источник: [docs/stage7_validation_report.md](docs/stage7_validation_report.md).

### GitHub Actions на `65de3ad`

Пять workflow завершились **SUCCESS** (см. таблицу в разделе этапа 4): CI Python, CI Docker, CI Infrastructure, CI Kubernetes, CI Airflow DAG.

---

## Инструкции по локальному запуску

### Требования

- Windows 11, PowerShell 5.1+
- Python 3.13 (проектный `.venv`)
- Docker Desktop — по необходимости (API / observability / Airflow)
- 8 ГБ RAM: не поднимайте одновременно observability + Airflow без запаса памяти

### Установка зависимостей

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt -r requirements-api.txt
# Для NN/ONNX-обучения и parity:
pip install -r requirements-nn.txt
$env:PYTHONPATH = (Get-Location).Path
```

### Inference API

```powershell
docker compose up -d --build
```

Проверка: http://127.0.0.1:8000/health/ready

### Тесты

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:OMP_NUM_THREADS = "1"
.\.venv\Scripts\python.exe -m pytest -q
```

### Monitoring / Retraining (без Docker)

```powershell
.\.venv\Scripts\python.exe -m src.monitoring.cli demo
.\.venv\Scripts\python.exe -m src.retraining.cli demo
```

---

## Ограничения проекта

- Учебный объём: акцент на воспроизводимость и честные артефакты, не на cloud production SLA.
- **Нет** выполненного `terraform apply` и **нет** production в Yandex Cloud.
- Реальные кредитные/персональные данные не хранятся в Git.
- Airflow не устанавливается в Windows `.venv`; Linux-контейнер — для локального Docker E2E.
- Airflow Docker E2E: `docs/stage7_airflow_e2e_report.md` (не путать с GHA parse-only CI).
- Default candidate backend этапа 7 — logistic + существующий preprocessor; полный MLP-retrain опционален и тяжелее по ресурсам.
- **Нет автоматического продвижения** challenger/candidate в production.

---

## Ссылки на техническую документацию

| Документ | Описание |
| --- | --- |
| [docs/implementation_plan.md](docs/implementation_plan.md) | План и аудит |
| [docs/requirements_matrix.md](docs/requirements_matrix.md) | Матрица требований 0–7 |
| [docs/architecture/overview.md](docs/architecture/overview.md) | Архитектура |
| [docs/architecture/observability.md](docs/architecture/observability.md) | Observability |
| [docs/api_contract.md](docs/api_contract.md) | API-контракт |
| [docs/model_benchmark.md](docs/model_benchmark.md) | Benchmark этапа 1 |
| [docs/docker_deployment.md](docs/docker_deployment.md) | Docker |
| [docs/kubernetes_local_deployment.md](docs/kubernetes_local_deployment.md) | kind / Kustomize |
| [docs/terraform_infrastructure.md](docs/terraform_infrastructure.md) | Terraform |
| [docs/cicd_pipeline.md](docs/cicd_pipeline.md) | CI/CD |
| [docs/stage5_runbook.md](docs/stage5_runbook.md) | Observability runbook |
| [docs/stage6_runbook.md](docs/stage6_runbook.md) | Drift / A/B runbook |
| [docs/stage7_runbook.md](docs/stage7_runbook.md) | Retraining / Airflow runbook |
| [docs/stage7_airflow_e2e_report.md](docs/stage7_airflow_e2e_report.md) | Airflow Docker E2E (A/A2/B/C/D/E + scheduler) |
| [docs/stage1_audit_report.md](docs/stage1_audit_report.md) … [docs/stage7_validation_report.md](docs/stage7_validation_report.md) | Отчёты валидации по этапам |
