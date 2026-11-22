# credit-scoring-mlops-deployment

Промышленное развертывание кредитной скоринговой системы (учебный итоговый проект).

**Статус:** этапы 0–2, **3А (kind)** и **3Б (Terraform IaC, без apply)** завершены.
Этап 4+ / Airflow / cloud apply — не начаты.

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
- [Terraform / Yandex Cloud](docs/terraform_infrastructure.md)
- [Оценка стоимости](docs/cloud_cost_estimate.md)
- [Валидация этапа 3Б](docs/stage3b_validation_report.md)

## Inference API (этап 2)

Backend: **ONNX FP32**, threshold **0.5**, artifacts:

- `models/preprocessor.joblib`
- `models/credit_scoring_nn.onnx`

### Local / Docker / kind

См. предыдущие разделы и `k8s/README.md`. Кратко:

```powershell
docker compose up -d
.\scripts\k8s_create.ps1; .\scripts\k8s_build_load.ps1; .\scripts\k8s_deploy.ps1; .\scripts\k8s_smoke.ps1
```

### Terraform (этап 3Б) — только static checks

```powershell
$tf = ".\tools\terraform.exe"   # Terraform v1.17.2 portable, или terraform в PATH
& $tf -chdir=infra/terraform fmt -recursive -check
& $tf -chdir=infra/terraform/environments/staging init -backend=false
& $tf -chdir=infra/terraform/environments/staging validate
```

**Запрещено без отдельного разрешения:** `terraform apply`, `destroy`, загрузка образов/моделей в облако.

Подробности: [infra/terraform/README.md](infra/terraform/README.md).

### Tests

```powershell
pytest -v
flake8 src tests
black --check src tests
kubectl kustomize k8s/overlays/local
```

## Baseline metrics (immutable)

RF test ROC-AUC **0.7771**; MLP test ROC-AUC **0.7742**.
