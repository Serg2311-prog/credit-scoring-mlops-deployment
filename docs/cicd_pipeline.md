# CI/CD Pipeline (Stage 4)

## Status

- GitHub Actions workflows are defined under `.github/workflows/`.
- **No git remote** was configured in the working copy at stage-4 implementation time → Actions cannot run until the repo is published and pushed.
- Local reproduction: `scripts/ci/check.ps1`, `build_images.ps1`, `smoke.ps1`.
- Cloud CD (`terraform apply`, YCR push) is **not** executed in stage 4.

## Workflows

| Workflow | Triggers | Purpose |
| --- | --- | --- |
| `ci-python.yml` | PR, push `main`, manual | black, flake8, pytest, synthetic artifacts |
| `ci-infrastructure.yml` | PR, push `main`, manual | terraform fmt/validate, kustomize, static k8s/tf tests |
| `ci-docker.yml` | PR, push `main`, manual | build API+models images, Trivy CRITICAL/HIGH |
| `ci-kubernetes.yml` | PR/push (manifests); kind smoke only on manual flag | dry-run + optional kind |
| `release-candidate.yml` | manual only | package RC metadata artifact (no GitHub Release) |
| `cd-staging.yml` | manual + confirm phrase | dry-run plan only, `SKIPPED_NO_CLOUD_CREDENTIALS` |

## Artifact strategy (Variant A)

Binary models and UCI CSV are **not** in Git.

CI generates deterministic **synthetic** ONNX + `preprocessor.joblib`:

```powershell
python scripts/ci/generate_synthetic_artifacts.py --output-dir models --force
python scripts/ci/verify_artifacts.py --dir models --allow-synthetic
```

Marker: `models/CI_SYNTHETIC_ARTIFACTS.json` (`synthetic: true`, `not_production: true`).

| Suite | Marker | CI behavior |
| --- | --- | --- |
| unit / contract integration | synthetic or real | **RUN** |
| `@pytest.mark.real_artifacts` | production only | **SKIP** on CI |
| kind smoke | optional | manual `run_kind_smoke=true` |

Do not treat CI-synthetic weights as stage-1 production (`mlp-onnx-fp32-v1`, dim 47).

## Local commands

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
.\scripts\ci\check.ps1                 # uses existing models/ if present
.\scripts\ci\build_images.ps1
.\scripts\ci\smoke.ps1 -ViaCompose     # requires Docker + artifacts
```

Terraform (no apply):

```powershell
terraform -chdir=infra/terraform fmt -recursive -check
$env:TF_VAR_cloud_id="ci..."
$env:TF_VAR_folder_id="ci..."
$env:TF_VAR_artifacts_bucket_name="ci-bucket"
terraform -chdir=infra/terraform/environments/staging init -backend=false
terraform -chdir=infra/terraform/environments/staging validate
```

## CD gate (future)

1. Configure GitHub Environment `staging` with required reviewers.
2. Run `cd-staging.yml` with `confirm=deploy-staging-dry-run`.
3. Separate explicit approval for `terraform plan` / `apply` and registry push (out of stage 4).

## Publishing the repo

```powershell
gh repo create <name> --private --source . --remote origin
git push -u origin main
```

Until `origin` exists, GitHub Actions status is **NOT EXECUTED** (workflows are ready).
