# Краткое руководство по запуску и проверке

Документ для локальной проверки репозитория на **CPU / ~8 GB RAM**: установка зависимостей, тесты, API/Compose, observability, drift demo и Terraform validate — без создания платных облачных ресурсов.

**Не поднимайте одновременно** observability + Airflow + kind на 8 GB.

Baseline релиза: commit `5527a55` / tag `v1.0.0`.

---

## 1. Архитектура (кратко)

Диаграммы: [`architecture/overview.md`](architecture/overview.md).

- Serving: FastAPI + ONNX FP32
- Observability: Prometheus / Grafana / Loki
- Drift и A/B: offline + online (локально)
- Retraining: Airflow, `auto_promote=false`
- Облако: эксперимент Yandex Managed Kubernetes — инфраструктура создана, проверена и уничтожена; ML-приложение в облаке **не** развёртывалось — [`../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md)

## 2. Где искать материалы по этапам

| Этап | Куда смотреть |
| --- | --- |
| Модель | `docs/model_benchmark.md`, `results/block7/` |
| Cloud / Terraform | `infra/terraform/`, `docs/terraform_infrastructure.md`, `results/block11/` |
| Docker / Kubernetes | `docker/`, `k8s/`, `docs/docker_deployment.md` |
| CI/CD | `.github/workflows/`, `docs/cicd_pipeline.md` |
| Monitoring | `monitoring/`, `results/block8/`, `docs/stage5_*` |
| Drift / A/B | `src/monitoring/`, `results/block8/`, `docs/stage6_*` |
| Airflow | `airflow_home/dags/`, `docs/stage7_*` |
| Документация | `README.md`, этот файл, `final_project_report.md` |

Полная матрица требований: [`requirements_matrix.md`](requirements_matrix.md).  
Индекс доказательств: [`evidence_index.md`](evidence_index.md).

---

## 3. Подготовка окружения

Из **корня репозитория** (Windows PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt -r requirements-api.txt -r requirements-nn.txt
$env:PYTHONPATH = (Get-Location).Path
```

### Артефакты моделей

- **Production-parity:** распаковать `instructor_model_pack.zip` в **корень** репозитория (файлы должны оказаться в `models/…`). Подробности и SHA256: [`instructor_model_pack.md`](instructor_model_pack.md).
- **Без production-архива** (чистый клон / CI-путь):

```powershell
# Только если production ONNX отсутствует. Без --force, чтобы не затереть production-файлы.
if (-not (Test-Path models\credit_scoring_nn.onnx)) {
  python scripts/ci/generate_synthetic_artifacts.py --output-dir models
}
```

Synthetic-артефакты **не** совпадают с production SHA256.

---

## 4. Локальный сценарий (CPU, ~8 GB)

### A. Тесты без Docker (~2–5 мин)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m pytest -m "not k8s and not e2e" -q
python -m black --check src tests scripts/ci airflow_home/dags
python -m flake8 src tests scripts/ci airflow_home/dags
```

Ожидаемые результаты `pytest -m "not k8s and not e2e"`:

| Артефакты в `models/` | Ожидание |
| --- | --- |
| Production (instructor pack / verified SHA256) | **236 passed, 2 skipped** |
| Synthetic (`generate_synthetic_artifacts.py`) | **232 passed, 6 skipped** (часть production-parity тестов пропускается) |

### B. API локально (~1 мин)

Требуются артефакты в `models/` (production pack или synthetic).

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

### D. Observability (отдельно, после `docker compose down` при нехватке RAM)

```powershell
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build --scale frontend=0
.\scripts\observability\check.ps1
# Grafana http://127.0.0.1:3000  Prometheus :9090
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
```

### E. Drift demo (без Docker)

```powershell
python -m src.monitoring.cli demo
# артефакты: artifacts/monitoring/; production registry не меняется
```

### F. Terraform без облака

```powershell
terraform -chdir=infra/terraform/environments/staging init -backend=false
terraform -chdir=infra/terraform/environments/staging validate
```

**Не выполнять** `terraform apply` в этом сценарии.

### G. Остановка сервисов

```powershell
docker compose down
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
docker compose -f docker-compose.yml -f docker-compose.ab.e2e.yml down
# Airflow / kind — см. соответствующие runbooks, если поднимались
```

---

## 5. Что открыть без запуска

| Тема | Файл |
| --- | --- |
| Holdout metrics RF vs MLP | `docs/model_benchmark.md` |
| GPU T4 | `results/block7/colab/hardened/`, `docs/gpu_benchmark_colab.md` |
| Log/metric alerts | `results/block8/log_alert_*.json`, `metric_alert_*.json` |
| Online A/B | `results/block8/online_ab_evidence.json` |
| Airflow E2E | `docs/stage7_airflow_e2e_report.md` |
| Ограничения | `docs/final_project_report.md` §19 |

---

## 6. Безопасность

- Не коммитить `.env` / `*.tfvars` / `backend.hcl` с ключами.
- Credentials Terraform — только через переменные окружения, не через CLI `access_key` / `secret_key`.
- Для локальной проверки документации **не** создавать платные ресурсы Yandex Cloud.
