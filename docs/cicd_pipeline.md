# CI/CD Pipeline (Stage 4)

## Status (verified 2026-11-22)

- GitHub Actions workflows under `.github/workflows/` are **live** on [Serg2311-prog/credit-scoring-mlops-deployment](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment).
- Hosted verification at commit [`86410e8`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/commit/86410e8dfb7cd39711eb07ac3d88ceb2447b1a67): Python, Docker+Trivy, Infrastructure, Kubernetes offline, **kind E2E**, Release Candidate, and Staging **dry-run** all **SUCCESS**.
- Full run table and incident history: [`docs/stage4_validation_report.md`](stage4_validation_report.md).
- Cloud CD (`terraform apply`, YCR push, Managed K8s deploy) is **not** executed in stage 4.
- The system is **not** deployed to production.

## Workflows

| Workflow | Triggers | Purpose | Hosted proof (2026-11-22) |
| --- | --- | --- | --- |
| `ci-python.yml` | PR, push `main`, manual | black, flake8, pytest, synthetic artifacts | [SUCCESS `45018989577`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989577) |
| `ci-infrastructure.yml` | PR, push `main`, manual | terraform fmt/validate, kustomize, static k8s/tf tests | [SUCCESS `45018989519`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989519) |
| `ci-docker.yml` | PR, push `main`, manual | build API+models images, Trivy CRITICAL/HIGH (action pinned by SHA) | [SUCCESS `45018989479`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989479) |
| `ci-kubernetes.yml` | PR/push (manifests); kind smoke only on manual flag | kustomize + **kubeconform** offline; optional kind E2E | offline [SUCCESS `45018989542`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989542); kind E2E [SUCCESS `45019576136`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45019576136) |
| `release-candidate.yml` | manual only | package RC metadata artifact (**synthetic**; no GitHub Release) | [SUCCESS `45020271258`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45020271258) |
| `cd-staging.yml` | manual + confirm phrase | **dry-run only**; no cloud apply without credentials | [SUCCESS `45020843911`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45020843911) |

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
| Block 7 GPU evidence integrity | always | reads `results/block7/colab/**` only (no `models/*.pt`) |
| Block 7 GPU↔production binding | `@pytest.mark.real_artifacts` | **SKIP** on hosted CI — PT gitignored; ONNX replaced by synthetic |

`results/block7/colab/**` is marked `-text` in `.gitattributes` so SHA256 manifests stay byte-stable across Windows/Linux checkouts.
| kind smoke | optional | manual `run_kind_smoke=true` |

Do not treat CI-synthetic weights as stage-1 production (`mlp-onnx-fp32-v1`, dim 47).
Kind smoke patches ConfigMap `EXPECTED_INPUT_DIM` / `MODEL_VERSION` from the synthetic marker via `scripts/ci/render_kind_manifests.py`.

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

## CD (Block 5 / 5.1)

| Workflow | Role |
| --- | --- |
| `ci-cd.yml` | Gate **5** required CI for SHA → modes `validation` / `publish` / `deploy` (fail-closed). Opt-in auto on `main` via `AUTO_STAGING_ENABLED=true` + `workflow_run`. GHCR `:sha` + digest; deploy writes `staging-release.json` |
| `cd-staging.yml` | Dry-run / documentation path (`confirm=deploy-staging-dry-run`) + CI gate |
| `cd-production.yml` | Fetch verified `staging-release.json` by `staging_run_id`; promote **same digests**; `environment: production`; main-only; modes `validation` / `deploy` |

**Required CI gate:** CI Python, CI Docker, CI Infrastructure, CI Kubernetes, CI Airflow DAG (same commit SHA). Incomplete checks wait on auto path; failed/cancelled/skipped/stale tip block deploy.

**Fail-closed:** `mode=deploy` without kubeconfig or smoke base URL → job failure (not false SUCCESS). Validation ≠ deployment.

Local kind verification (not cloud): `scripts/ci/local_cd_verify.ps1` → namespaces `credit-scoring-cd-staging` / `credit-scoring-cd-prod`.

Report: [`docs/stage4_cicd_completion_report.md`](stage4_cicd_completion_report.md).

1. Configure GitHub Environments `staging` / `production` (reviewers in UI — not claimed until configured).
2. Set secrets/vars listed in the completion report (no values in Git). Optional repo var `AUTO_STAGING_ENABLED=true`.
3. `terraform apply` remains **out of policy** until explicitly approved.

## Fixes after hosted CI (summary)

1. **Kubernetes offline:** kubeconform instead of `kubectl apply --dry-run=client`.
2. **Trivy action:** pinned SHA v0.36.0; HIGH/CRITICAL gate retained.
3. **Actions pinning:** full commit SHAs.
4. **Trivy `CVE-2025-47273` / Alpine `musl`:** Dockerfile + constraints; gate unchanged.
5. **kind disk pressure:** runner reclaim, build-before-kind, image slim, diagnostics.
6. **kind rollout / synthetic dim:** render ConfigMap from synthetic marker before apply.

Non-critical hosted warnings (do not fail gates): Node.js 20 deprecation notices; Docker Buildx cache save (`tar` exit code 2).
