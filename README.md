# credit-scoring-mlops-deployment

**Промышленное развёртывание кредитной скоринговой системы с полным MLOps-циклом**

Учебный итоговый проект по дисциплине «Автоматизация процессов доставки и развертывания моделей машинного обучения».

| | |
| --- | --- |
| Baseline commit | `bdb8b43` |
| Cloud experiment (`cloud-experiment`) | **выполнен и уничтожен** (MK8s v1.34.1, 1×CPU 4/16/64) — см. [`results/block11/`](results/block11/) |
| Remote State | **был** в Object Storage (live); бакет и ключи **удалены** после destroy |
| Cloud ML-приложение / GHCR publish | **ABORT_CLOUD_APP** (образы локально; push/deploy не выполнялись) |
| Production Yandex Cloud | **не развёрнут** (отдельное env; не трогался) |
| Serving default | ONNX Runtime **CPU FP32** |
| Auto-promote challenger | **`false`** |

Исходный ML-проект: [credit-default-prediction](https://github.com/Serg2311-prog/credit-default-prediction).

---

## Постановка задачи

Кредитный скоринг (UCI / Taiwan credit card default) нужно перевести из учебного notebook-контура в воспроизводимый MLOps-контур: обучение → ONNX → API → контейнеры/K8s → IaC → CI/CD → observability → drift/A/B → Airflow retraining — **без фиктивных метрик и без неподтверждённого cloud production**.

## Цель и результаты

- Совместимая **PyTorch MLP** на той же схеме признаков, что и исторический RF baseline.
- Production-кандидат инференса: **ONNX FP32** (parity с PyTorch; test ROC-AUC **0.7742**).
- RF baseline test ROC-AUC **0.7771** (не подменяется).
- Dynamic INT8 quantization как **экспериментальный** артефакт (не auto-champion).
- Локально проверены: Docker Compose, kind/Kustomize, Prometheus/Grafana/Loki, drift, online A/B, Airflow Docker E2E.
- CI: GitHub Actions quality/security gates (см. [`docs/cicd_pipeline.md`](docs/cicd_pipeline.md)).
- Облако (Block 11): Terraform Apply + Remote State + Managed Kubernetes + Ready worker + Calico + Metrics Server — **runtime-проверены**, затем **destroy verified**. Cloud app — **ABORT_CLOUD_APP**. Итог: [`results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md).

Подробный сводный отчёт: [`docs/final_project_report.md`](docs/final_project_report.md). Статус облака: [`results/block11/CLOUD_RUNTIME_VERIFICATION.md`](results/block11/CLOUD_RUNTIME_VERIFICATION.md).

---

## Архитектура

Кратко:

```text
Client / Frontend → FastAPI (ONNX FP32) → /metrics + JSON logs
                         ↓
              Prometheus / Grafana / Loki / Alertmanager
                         ↓
         Evidently drift + A/B + Airflow retraining (candidate only)
                         ↓
         Terraform (Yandex Cloud: experiment applied → destroyed; app ABORT)
```

Диаграммы Mermaid: [`docs/architecture/overview.md`](docs/architecture/overview.md).

## Технологический стек

| Слой | Стек |
| --- | --- |
| ML | PyTorch, scikit-learn, ONNX Runtime, Evidently |
| API / UI | FastAPI, nginx frontend |
| Data | DVC, Pandera |
| Containers | Docker multi-stage, Compose |
| K8s | kind, Kustomize, Ingress, NetworkPolicy |
| IaC | Terraform (Yandex Cloud modules) |
| CI/CD | GitHub Actions, Trivy, kubeconform |
| Observability | Prometheus, Grafana, Loki, Alloy, Alertmanager |
| Retraining | Apache Airflow 2.9.x DAG |

## Датасет

- **UCI Credit Card Default** (Taiwan): бинарный default payment.
- Сырые признаки + feature engineering → preprocessor → модель.
- В Git **нет** реальных PII клиентов; CI использует synthetic ONNX/joblib.
- DVC pipeline: `dvc.yaml` / `dvc.lock` (local remote `.dvc_remote/`, gitignored).

## Структура репозитория

```text
src/                 # API, NN, monitoring, retraining
models/              # production ONNX/PT/preprocessor/registry (immutable без retrain)
frontend/            # nginx UI
docker/              # Dockerfiles
k8s/                 # Kustomize base + overlays
infra/terraform/     # Yandex Cloud modules + envs
monitoring/          # Prometheus/Grafana/Loki/Alloy/Alertmanager
airflow_home/dags/   # retraining DAG
configs/             # thresholds, retraining, monitoring
docs/                # отчёты, runbooks, архитектура
results/block7|8|9/  # evidence
tests/               # pytest
.github/workflows/   # CI/CD
```

## Системные требования

| Режим | Минимум |
| --- | --- |
| Unit tests / monitoring CLI | Python 3.11+, ~4 GB RAM |
| API + frontend Compose | Docker Desktop, ~4–6 GB свободно |
| Observability stack | +~2 GB; **не** поднимать вместе с Airflow на 8 GB |
| kind | Docker + kubectl; NetworkPolicy enforcement на kindnet **не подтверждён** |
| GPU benchmark | Colab T4 evidence уже в `results/block7/` (локально GPU может отсутствовать) |

---

## Быстрый старт

### Windows PowerShell

```powershell
git clone <repo-url>
cd credit-scoring-mlops-deployment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
# Match CI: runtime + API + NN + dev tools (requirements-dev alone is not enough)
pip install -r requirements.txt -r requirements-dev.txt -r requirements-api.txt -r requirements-nn.txt
$env:PYTHONPATH = (Get-Location).Path
# Without local production models/, generate CI synthetic artifacts first:
#   python scripts/ci/generate_synthetic_artifacts.py --output-dir models --force
python -m pytest -m "not k8s and not e2e" -q
```

### Linux / Bash

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt -r requirements-api.txt -r requirements-nn.txt
export PYTHONPATH="$PWD"
# python scripts/ci/generate_synthetic_artifacts.py --output-dir models --force
python -m pytest -m "not k8s and not e2e" -q
```

Production ONNX/PT/preprocessor are **gitignored** (not DVC outs). For production-parity inference see [`docs/instructor_model_pack.md`](docs/instructor_model_pack.md).

---

## API

```powershell
$env:PYTHONPATH = (Get-Location).Path
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
# http://127.0.0.1:8000/health/ready
# http://127.0.0.1:8000/docs
# POST /predict  — см. docs/api_contract.md
```

Контракт: [`docs/api_contract.md`](docs/api_contract.md).

## Frontend

```powershell
docker compose up -d --build
# UI: http://127.0.0.1:8081  (проксирует /api → api:8000)
docker compose down
```

## Docker Compose

```powershell
# Inference only
docker compose up -d --build --scale frontend=0

# Observability (после/вместо тяжёлых стеков — последовательно на 8 GB)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build --scale frontend=0
.\scripts\observability\check.ps1
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
```

| Сервис | URL |
| --- | --- |
| API | http://127.0.0.1:8000 |
| Frontend | http://127.0.0.1:8081 |
| Grafana | http://127.0.0.1:3000 |
| Prometheus | http://127.0.0.1:9090 |
| Alertmanager | http://127.0.0.1:9093 |

## Kubernetes (local kind)

```powershell
.\scripts\k8s_create.ps1          # при необходимости
.\scripts\k8s_ingress_e2e.ps1
# NetworkPolicy manifests: verified; kindnet enforcement = не runtime-подтверждён
```

Подробности: [`docs/kubernetes_local_deployment.md`](docs/kubernetes_local_deployment.md), [`k8s/README.md`](k8s/README.md).

## DVC

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m dvc repro
python -m dvc push
docker build -f docker/Dockerfile.dvcdata -t credit-scoring-dvc-data:local .
```

Smoke-train в DVC **не** перезаписывает production `models/*`.

## Monitoring & alerting

```powershell
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build --scale frontend=0
.\.venv\Scripts\python.exe scripts\observability\verify_stack.py
# Runbook: docs/stage5_runbook.md
# Block 8 evidence: results/block8/
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
```

## Drift detection

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m src.monitoring.cli demo
# пишет demo artifacts в artifacts/monitoring/; production registry не меняет
pytest tests/monitoring -q
```

Отчёты: [`docs/stage6_drift_completion_report.md`](docs/stage6_drift_completion_report.md), [`docs/stage6_runbook.md`](docs/stage6_runbook.md).

## Online A/B

По умолчанию `AB_ENABLED=false`. Изолированная проверка (champion FP32 + experimental quant challenger):

```powershell
docker compose -f docker-compose.yml -f docker-compose.ab.e2e.yml up -d --no-build --scale frontend=0
.\.venv\Scripts\python.exe scripts\block8\e2e_online_ab.py --n-ids 1000 --n-http 150
docker compose -f docker-compose.yml -f docker-compose.ab.e2e.yml down
```

Evidence: [`results/block8/online_ab_evidence.json`](results/block8/online_ab_evidence.json).
Это **synthetic HTTP**, не трафик реальных клиентов. `auto_promote=false`.

## Airflow retraining

```powershell
# Полный локальный E2E (тяжёлый — не параллелить с observability)
# см. docs/stage7_runbook.md и docs/stage7_airflow_e2e_report.md
docker compose -f docker-compose.airflow.yml -f docker-compose.airflow.e2e.yml ...
```

Решение о retrain: triggers по drift/quality; кандидат в isolated run dir; **без** auto-promote в production registry.

## Terraform

```powershell
terraform -chdir=infra/terraform fmt -recursive -check
terraform -chdir=infra/terraform/environments/staging init -backend=false
terraform -chdir=infra/terraform/environments/staging validate
```

Remote state examples: `backend.hcl.example` + credentials **только через env** (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`).
**Не** передавать `access_key`/`secret_key` через `-backend-config=` CLI.
Дополнительный apply/destroy — **только** с явным одобрением (кластер уже потребляет грант). Experiment env: `infra/terraform/environments/cloud-experiment`.

## CI/CD

Workflows: `.github/workflows/` (`ci-python`, `ci-docker`+Trivy, `ci-infrastructure`, `ci-kubernetes`, `ci-airflow-dag`, orchestrator `ci-cd.yml`, CD dry-run).

Локально:

```powershell
.\scripts\ci\check.ps1
```

## Тестирование

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest -m "not k8s and not e2e" -q
python -m black --check src tests scripts/ci airflow_home/dags
python -m flake8 src tests scripts/ci airflow_home/dags
```

На baseline `0df191a`: **231 passed, 2 skipped** (локально, Block 8.1).

## CPU / GPU benchmark

| Контур | Статус | Evidence |
| --- | --- | --- |
| CPU model_only + quality | VERIFIED_LOCAL | `results/block7/`, `docs/model_benchmark.md` |
| API HTTP load (synthetic) | VERIFIED_LOCAL | `results/block7/api_load_summary.json` |
| GPU Colab Tesla T4 | VERIFIED_GPU | `results/block7/colab/hardened/` |
| GPU INT8 / GPU HTTP load | **не выполнялись** | — |

Не смешивать model-only throughput с HTTP throughput; не смешивать synthetic GPU latency с holdout quality.

## Безопасность

- Trivy gate в CI Docker.
- Secrets не в Git; `.env.example` без реальных ключей.
- Terraform backends — env credentials only.
- E2E log probe вынесен из production API.
- `results/block8/_raw_encoding_backup/` gitignored.

## Ограничения (честно)

- **CLOUD_INFRA (experiment):** Remote State + Apply + MK8s v1.34.1 + Ready worker + Calico + Metrics Server — **runtime verified**, затем **destroy verified** ([`results/block11/`](results/block11/))
- **CLOUD_APP:** GHCR push / cloud inference / HPA / NP enforcement / cloud monitoring / rolling update / rollback — **ABORT_CLOUD_APP** (не утверждаются)
- **Production** Terraform env — **не развёрнут**
- SG rules: 12 standalone resources + dependency guard; dual-managed wipe remediated
- Периодические `kubectl` TLS handshake timeout — наблюдались; причина **не установлена**
- Experimental API image (trixie, **not in delivery**): Trivy 53 HIGH / 0 CRITICAL historically — see `results/block11/`; delivery `Dockerfile.api` = `main` bookworm; merge-prep Trivy gate PASS
- GPU node group в облаке — **не запускалась**
- NetworkPolicy enforcement на kind — **не runtime-подтверждён**; наличие Calico ≠ enforcement конкретных NP
- cAdvisor на Docker Desktop: нет label `name` у контейнеров
- Online A/B challenger = existing quantized ONNX (эксперимент)
- Controlled concept-drift experiment ≠ production concept drift proof
- Airflow E2E — локальный Docker, не managed cloud

Финальный аудит: [`results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md). Scorecard: [`results/block11/FINAL_PROJECT_SCORECARD.md`](results/block11/FINAL_PROJECT_SCORECARD.md).

---

## Документация и evidence

| Документ | Назначение |
| --- | --- |
| [`docs/final_project_report.md`](docs/final_project_report.md) | Сводный отчёт |
| [`docs/requirements_matrix.md`](docs/requirements_matrix.md) | Матрица соответствия ТЗ |
| [`docs/evidence_index.md`](docs/evidence_index.md) | Навигация по доказательствам |
| [`docs/quick_review.md`](docs/quick_review.md) | Инструкция для преподавателя |
| [`docs/defense_guide.md`](docs/defense_guide.md) | Подготовка к защите |
| [`docs/architecture/overview.md`](docs/architecture/overview.md) | Архитектура + Mermaid |
| [`results/block7/`](results/block7/) | CPU/GPU/API load evidence |
| [`results/block8/`](results/block8/) | Monitoring / drift / A/B evidence |
| [`results/block11/`](results/block11/) | Cloud experiment + final closure reports |

Проект охватывает полный MLOps-цикл: подготовку и оптимизацию моделей, облачную инфраструктуру, контейнеризацию и оркестрацию, CI/CD, мониторинг, обнаружение дрейфа данных, A/B-тестирование и автоматизацию переобучения.
