# credit-scoring-mlops-deployment

Промышленное развертывание кредитной скоринговой системы (учебный итоговый проект).

**Статус:** этапы 0–2 и **проектный этап 3А (Kubernetes local / kind)** завершены.  
Этап 3Б / Terraform / Airflow — не начаты.

Исходный ML-проект: [credit-default-prediction](https://github.com/Serg2311-prog/credit-default-prediction).

## Документы

- [План](docs/implementation_plan.md)
- [Матрица требований](docs/requirements_matrix.md)
- [Benchmark модели](docs/model_benchmark.md)
- [Аудит этапа 1](docs/stage1_audit_report.md)
- [API contract](docs/api_contract.md)
- [Docker](docs/docker_deployment.md)
- [Валидация этапа 2](docs/stage2_validation_report.md)
- [Kubernetes local](docs/kubernetes_local_deployment.md)
- [Валидация этапа 3А](docs/stage3a_validation_report.md)

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

### Docker Compose

```powershell
docker compose build
docker compose up -d
docker compose down
```

### Kubernetes local (этап 3А)

```powershell
# kind portable (once)
New-Item -ItemType Directory -Force -Path tools | Out-Null
curl.exe -fsSL -o tools\kind.exe https://kind.sigs.k8s.io/dl/v0.29.0/kind-windows-amd64

.\scripts\k8s_create.ps1
.\scripts\k8s_build_load.ps1
.\scripts\k8s_deploy.ps1
.\scripts\k8s_smoke.ps1
```

Доступ: `kubectl -n credit-scoring port-forward svc/credit-scoring-api 8000:8000`  
Подробности: [k8s/README.md](k8s/README.md), [docs/kubernetes_local_deployment.md](docs/kubernetes_local_deployment.md).

### Tests

```powershell
pytest -v
flake8 src tests
black --check src tests
kubectl kustomize k8s/overlays/local
```

## Baseline metrics (immutable)

RF test ROC-AUC **0.7771**; MLP test ROC-AUC **0.7742**.
