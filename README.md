# credit-scoring-mlops-deployment

Промышленное развертывание кредитной скоринговой системы (учебный итоговый проект).

**Статус:** этапы **0–7** реализованы в репозитории.
Этап 4 CI/CD **проверен на GitHub Actions**. Этап 5 — **локальный** observability-стек (без облака).
Этап 6 — offline drift / quality signal / A/B (Evidently `0.7.23`, без auto-promote).
Этап 7 — Airflow retraining pipeline (engine + DAG + compose; **без auto-promote**).
Cloud `terraform apply` — не выполнялся. Production в облаке **не развёрнут**.

Исходный ML-проект: [credit-default-prediction](https://github.com/Serg2311-prog/credit-default-prediction).

## Документы

- [План](docs/implementation_plan.md)
- [Матрица требований](docs/requirements_matrix.md)
- [Архитектура](docs/architecture/overview.md) · [Observability](docs/architecture/observability.md)
- [API / Docker / K8s / Terraform](docs/) — отчёты этапов 2–3
- [CI/CD](docs/cicd_pipeline.md) · [Валидация этапа 4](docs/stage4_validation_report.md)
- [Stage 5 runbook](docs/stage5_runbook.md) · [Валидация этапа 5](docs/stage5_validation_report.md)
- [Stage 6 runbook](docs/stage6_runbook.md) · [Валидация этапа 6](docs/stage6_validation_report.md)
- [Stage 7 runbook](docs/stage7_runbook.md) · [Валидация этапа 7](docs/stage7_validation_report.md)

## Inference API

Backend: **ONNX FP32**, threshold **0.5**.

```powershell
docker compose up -d --build
# http://127.0.0.1:8000/health/ready
```

## Observability (этап 5, локально)

```powershell
# API + Prometheus + Grafana + Loki + Alloy + Alertmanager (+ cAdvisor)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build

# Проверки
.\scripts\observability\check.ps1
.\scripts\observability\fire_test_alert.ps1
```

| UI | URL |
| --- | --- |
| Grafana | http://127.0.0.1:3000 (admin/admin) |
| Prometheus | http://127.0.0.1:9090 |
| Alertmanager | http://127.0.0.1:9093 |
| API metrics | http://127.0.0.1:8000/metrics |

Подробности: [docs/stage5_runbook.md](docs/stage5_runbook.md).

## Monitoring Stage 6 (drift / A/B)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:OMP_NUM_THREADS = "1"
.\.venv\Scripts\python.exe -m src.monitoring.cli demo
# reports → artifacts/monitoring/
```

| Command | Purpose |
| --- | --- |
| `data-drift` | Evidently feature drift (target excluded) |
| `concept-drift` | Labeled quality degradation **signal** |
| `ab-offline` | Same-holdout champion vs challenger |
| `demo` | Synthetic end-to-end artifacts |

Пороги: `configs/monitoring/stage6_thresholds.yaml`. Runbook: [docs/stage6_runbook.md](docs/stage6_runbook.md).

## Retraining Stage 7 (Airflow-ready engine)

Airflow **не ставится** в Windows `.venv`. Локально используйте CLI; Airflow — отдельный Linux Docker.

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
$env:OMP_NUM_THREADS = "1"
.\.venv\Scripts\python.exe -m src.retraining.cli demo
.\.venv\Scripts\python.exe -m src.retraining.cli dry-run --input path\to\data.csv --modes scheduled
# Docker (опционально, ресурсоёмко — не запускать без необходимости):
# docker compose -f docker-compose.airflow.yml up --build
```

| Command | Purpose |
| --- | --- |
| `validate-data` | Schema / target / class checks |
| `check-triggers` | scheduled / data_drift / quality_drop |
| `dry-run` | Full pipeline without production registry write |
| `train-candidate` | Train + evaluate + register candidate |
| `demo` | Synthetic dry-run |

Пороги: `configs/retraining/stage7.yaml`. Runbook: [docs/stage7_runbook.md](docs/stage7_runbook.md).

## Local CI checks (этап 4)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
.\scripts\ci\check.ps1
.\scripts\ci\build_images.ps1
```

GitHub Actions: `.github/workflows/` — см. [docs/stage4_validation_report.md](docs/stage4_validation_report.md).

## kind / Terraform

```powershell
.\scripts\k8s_create.ps1; .\scripts\k8s_build_load.ps1; .\scripts\k8s_deploy.ps1; .\scripts\k8s_smoke.ps1

terraform -chdir=infra/terraform fmt -recursive -check
terraform -chdir=infra/terraform/environments/staging init -backend=false
terraform -chdir=infra/terraform/environments/staging validate
# terraform apply — только с явным разрешением
```

## Baseline metrics (immutable)

RF test ROC-AUC **0.7771**; MLP test ROC-AUC **0.7742**.
