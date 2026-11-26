# Быстрый обзор для преподавателя

Цель документа: за 20–40 минут найти реализацию критериев ТЗ, прогнать облегчённые проверки на **CPU / ~8 GB RAM** и открыть evidence без платных облачных ресурсов.

**Не поднимайте одновременно** observability + Airflow + kind на 8 GB.

Baseline: commit `0df191a`.

---

## 1. Архитектура за 2 минуты

См. диаграммы: [`architecture/overview.md`](architecture/overview.md).
Serving: FastAPI + ONNX FP32. Observability: Prometheus/Grafana/Loki. Drift/A/B offline+online. Retraining: Airflow, `auto_promote=false`. Cloud: Block 11 `cloud-experiment` apply→destroy; app `ABORT_CLOUD_APP` — [`../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md).

## 2. Где искать критерии

| Этап ТЗ (макс.) | Куда смотреть |
| --- | --- |
| Модель (5) | `docs/model_benchmark.md`, `results/block7/` |
| Cloud (7) | `infra/terraform/`, `docs/terraform_infrastructure.md`, `results/block11/` |
| Docker/K8s (8) | `docker/`, `k8s/`, `docs/docker_deployment.md` |
| CI/CD (5) | `.github/workflows/`, `docs/cicd_pipeline.md` |
| Monitoring (8) | `monitoring/`, `results/block8/`, `docs/stage5_*` |
| Drift (7) | `src/monitoring/`, `results/block8/`, `docs/stage6_*` |
| Airflow (5) | `airflow_home/dags/`, `docs/stage7_*` |
| Docs (5) | `README.md`, этот файл, `final_project_report.md` |

Полная матрица: [`requirements_matrix.md`](requirements_matrix.md).
Индекс evidence: [`evidence_index.md`](evidence_index.md).

---

## 3. Облегчённый сценарий (CPU, 8 GB)

### A. Тесты без Docker (~2–5 мин)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m pytest -m "not k8s and not e2e" -q
python -m black --check src tests scripts/ci airflow_home/dags
python -m flake8 src tests scripts/ci airflow_home/dags
```

Ожидание: порядка **231 passed, 2 skipped**.

### B. API локально (~1 мин)

```powershell
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
# другой терминал:
Invoke-RestMethod http://127.0.0.1:8000/health/ready
# OpenAPI: http://127.0.0.1:8000/docs
```

### C. Compose API + frontend (~3–5 мин)

```powershell
docker compose up -d --build
# UI http://127.0.0.1:8081
# API http://127.0.0.1:8000
docker compose down
```

### D. Observability (отдельно, после down Compose при нехватке RAM)

```powershell
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build --scale frontend=0
.\scripts\observability\check.ps1
# Grafana http://127.0.0.1:3000  Prometheus :9090
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
```

### E. Drift demo (без Docker)

```powershell
python -m src.monitoring.cli demo
# artifacts/monitoring/; production registry не меняется
```

### F. Terraform без облака

```powershell
terraform -chdir=infra/terraform/environments/staging init -backend=false
terraform -chdir=infra/terraform/environments/staging validate
```

**Не выполнять** `terraform apply`.

### G. Остановка всего

```powershell
docker compose down
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
docker compose -f docker-compose.yml -f docker-compose.ab.e2e.yml down
# Airflow / kind — см. соответствующие runbooks, если поднимались
```

---

## 4. Что открыть без запуска

| Тема | Файл |
| --- | --- |
| Holdout metrics RF vs MLP | `docs/model_benchmark.md` |
| GPU T4 | `results/block7/colab/hardened/`, `docs/gpu_benchmark_colab.md` |
| Log/metric alerts | `results/block8/log_alert_*.json`, `metric_alert_*.json` |
| Online A/B | `results/block8/online_ab_evidence.json` |
| Airflow E2E | `docs/stage7_airflow_e2e_report.md` |
| Ограничения | `docs/final_project_report.md` §19 |

---

## 5. Безопасность при проверке

- Не коммитить `.env` / `*.tfvars` / `backend.hcl` с ключами.
- Credentials Terraform — только env, не CLI `access_key`/`secret_key`.
- Не требовать создание платных ресурсов Yandex Cloud для приёмки документации.
