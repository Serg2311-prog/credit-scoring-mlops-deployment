# credit-scoring-mlops-deployment

Промышленное развертывание кредитной скоринговой системы (учебный итоговый проект).

**Статус:** этапы 0–3Б и **этап 4 (CI/CD definitions)** завершены.
Cloud `terraform apply` / Airflow / этап 5 — не начаты.

Исходный ML-проект: [credit-default-prediction](https://github.com/Serg2311-prog/credit-default-prediction).

## Документы

- [План](docs/implementation_plan.md)
- [Матрица требований](docs/requirements_matrix.md)
- [API / Docker / K8s / Terraform](docs/) — см. соответствующие отчёты этапов
- [CI/CD](docs/cicd_pipeline.md)
- [Валидация этапа 4](docs/stage4_validation_report.md)

## Inference API

Backend: **ONNX FP32**, threshold **0.5**.

### Local CI checks (этап 4)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
.\scripts\ci\check.ps1
.\scripts\ci\build_images.ps1
```

GitHub Actions: `.github/workflows/` (`ci-python`, `ci-infrastructure`, `ci-docker`, `ci-kubernetes`, `release-candidate`, `cd-staging`).

> В рабочей копии **нет git remote** — hosted Actions выполнятся после `git remote add` + push (не делается автоматически).

### Docker / kind

```powershell
docker compose up -d
.\scripts\k8s_create.ps1; .\scripts\k8s_build_load.ps1; .\scripts\k8s_deploy.ps1; .\scripts\k8s_smoke.ps1
```

### Terraform (без apply)

```powershell
terraform -chdir=infra/terraform fmt -recursive -check
terraform -chdir=infra/terraform/environments/staging init -backend=false
terraform -chdir=infra/terraform/environments/staging validate
```

## Baseline metrics (immutable)

RF test ROC-AUC **0.7771**; MLP test ROC-AUC **0.7742**.
