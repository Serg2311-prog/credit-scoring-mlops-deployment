# credit-scoring-mlops-deployment

Промышленное развертывание кредитной скоринговой системы (учебный итоговый проект).

**Статус:** этапы 0–1 и **проектный этап 2 (Inference API + Docker)** завершены.  
Terraform / Kubernetes / Airflow — не начаты.

Исходный ML-проект: [credit-default-prediction](https://github.com/Serg2311-prog/credit-default-prediction).

## Документы

- [План](docs/implementation_plan.md)
- [Матрица требований](docs/requirements_matrix.md)
- [Benchmark модели](docs/model_benchmark.md)
- [Аудит этапа 1](docs/stage1_audit_report.md)
- [API contract](docs/api_contract.md)
- [Docker](docs/docker_deployment.md)
- [Валидация этапа 2](docs/stage2_validation_report.md)

## Inference API (этап 2)

Backend: **ONNX FP32**, threshold **0.5**, artifacts:

- `models/preprocessor.joblib`
- `models/credit_scoring_nn.onnx`

### Local

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt -r requirements-nn.txt -r requirements-api.txt
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Проверки: `/docs`, `/health/live`, `/health/ready`, `/model/info`, `/metrics`, `POST /predict`.

### Docker

```powershell
docker compose build
docker compose up -d
docker compose ps
docker compose down
```

Артефакты монтируются read-only. Без них `/health/ready` = 503.

### Tests

```powershell
pytest -v
flake8 src tests
black --check src tests
```

## Baseline metrics (immutable)

RF test ROC-AUC **0.7771**; MLP test ROC-AUC **0.7742**.
