# Stage 4 Validation Report — CI/CD

**Date checked:** 2026-11-22
**Git SHA:** [`86410e8dfb7cd39711eb07ac3d88ceb2447b1a67`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/commit/86410e8dfb7cd39711eb07ac3d88ceb2447b1a67)
**Repository:** [Serg2311-prog/credit-scoring-mlops-deployment](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment)
**Scope:** GitHub Actions CI/CD definitions, hosted-runner verification, synthetic CI artifacts, local check scripts
**Stage 5 / production cloud:** **not started / not deployed**

## Executive summary

Stage 4 CI/CD is **verified on GitHub-hosted runners** for Python quality gates, Docker build + Trivy, Terraform/Kustomize offline checks, Kubernetes offline validation, optional **kind E2E smoke**, Release Candidate packaging, and Staging **dry-run** CD.

This does **not** mean the system is deployed to Yandex Cloud, a public registry, or production. No cloud credentials were used for real apply/push.

## Confirmed GitHub Actions results

| Workflow | Result | Run | Link |
| --- | --- | --- | --- |
| CI Python | **SUCCESS** | `45018989577` | [actions/runs/45018989577](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989577) |
| CI Docker + Trivy | **SUCCESS** | `45018989479` | [actions/runs/45018989479](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989479) |
| CI Infrastructure | **SUCCESS** | `45018989519` | [actions/runs/45018989519](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989519) |
| CI Kubernetes (offline manifests) | **SUCCESS** | `45018989542` | [actions/runs/45018989542](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989542) |
| Kubernetes kind E2E (`run_kind_smoke=true`) | **SUCCESS** | `45019576136` | [actions/runs/45019576136](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45019576136) |
| Release Candidate | **SUCCESS** | `45020271258` | [actions/runs/45020271258](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45020271258) |
| CD Staging dry-run | **SUCCESS** | `45020843911` | [actions/runs/45020843911](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45020843911) |

### Kubernetes kind E2E (hosted)

Run [`45019576136`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45019576136) completed successfully on `ubuntu-latest`, including:

1. Hosted-runner disk reclaim
2. Synthetic artifact generation
3. Docker build of API + models images
4. kind cluster create
5. `kind load docker-image` for both images
6. Apply of rendered Kustomize manifests (ConfigMap aligned to synthetic dim)
7. Deployment rollout to Available
8. HTTP smoke via port-forward: `/health/live`, `/health/ready`, `/predict`, `/metrics`
9. kind cluster delete (`if: always()`)

## What was fixed during Stage 4 (incident history)

### 1. Initial CI configuration

| Failure | Fix |
| --- | --- |
| `kubectl apply --dry-run=client` needing OpenAPI / `localhost:8080` | Offline **kubeconform v0.6.7** (`-strict`, k8s `1.33.0`) |
| Invalid `aquasecurity/trivy-action@0.28.0` | Pin to SHA `ed142fd…` (**v0.36.0**) |
| Floating action tags | Full 40-hex SHA pins for checkout/setup-*/upload-artifact/buildx/terraform/kubectl |

### 2. Docker image blocking vulnerabilities

| Item | Detail |
| --- | --- |
| Early fail | Trivy API scan, run `45012291531` — `CVE-2025-47273` HIGH (phantom `setuptools@70.3.0` from pip `bom.cdx.json`) |
| Models | `CVE-2026-107891` HIGH in Alpine 3.20 `musl` → base **alpine:3.22** + upgrade |
| Remediation | `setuptools>=78.1.1`, delete vendored SBOM, slim venv; gate kept (`CRITICAL,HIGH`, `ignore-unfixed`, `exit-code: 1`) |
| Confirmed green | CI Docker + Trivy run [`45018989479`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45018989479) |

### 3. kind load — no space left on device

| Item | Detail |
| --- | --- |
| Fail run | `45015363021` — `kind load` API image → `no space left on device` |
| Cause | ~14 GB free on hosted runner; peak = torch + build cache + kindest/node + ~2× API image |
| Mitigations | `free_runner_disk.sh`, disk reports, build-before-kind, builder prune, CPU torch, API image slim (~840 MB → ~595 MB) |
| Confirmed green | kind E2E [`45019576136`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45019576136) |

### 4. kind rollout timeout — synthetic dim vs ConfigMap

| Item | Detail |
| --- | --- |
| Fail run | `45017625451` — `rollout status` timeout, 0 available replicas |
| Cause | Synthetic ONNX/preprocessor **input_dim=43** vs ConfigMap **EXPECTED_INPUT_DIM=47** → load error → `/health/ready` 503 |
| Fix | `render_kind_manifests.py` patches ConfigMap from `CI_SYNTHETIC_ARTIFACTS.json` before apply; diagnostics artifact before `kind delete` |
| Confirmed green | kind E2E [`45019576136`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45019576136) |

## Release Candidate

| Item | Status |
| --- | --- |
| Workflow | `release-candidate.yml` |
| Hosted result | **SUCCESS** — [`45020271258`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45020271258) |
| Artifacts | Synthetic ONNX + preprocessor + RC metadata package |
| GitHub Release | **Not created** (by design) |
| Production model | **Not** claimed; marker `synthetic: true`, `not_production: true` |

RC is a **packaging / reproducibility gate**, not a published product release.

## CD Staging

| Item | Status |
| --- | --- |
| Workflow | `cd-staging.yml` |
| Hosted result | **SUCCESS** — [`45020843911`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45020843911) |
| Mode | **dry-run only** (`confirm=deploy-staging-dry-run`) |
| Terraform apply | **Not executed** |
| Registry push / cluster deploy | **Not executed** |
| Cloud credentials | **Not used** for real cloud operations |

## Confirmed vs not executed

### Confirmed on GitHub-hosted runners

- Python: black, flake8, pytest (with synthetic CI artifacts where applicable)
- Docker build of API + models images
- Trivy CRITICAL/HIGH gate (`ignore-unfixed`)
- Terraform fmt/validate (no apply)
- Kustomize render + kubeconform offline
- kind create → load images → apply → rollout → HTTP smoke → delete cluster
- RC metadata packaging (synthetic)
- Staging CD dry-run path without cloud credentials

### Not executed (explicitly out of Stage 4 success claims)

| Activity | Status |
| --- | --- |
| Production deployment | **NOT EXECUTED** |
| Staging/production `terraform apply` | **NOT EXECUTED** |
| Real image publish to Yandex Container Registry (or other registry) | **NOT EXECUTED** |
| Cloud Kubernetes E2E (Managed K8s) | **NOT EXECUTED** |
| Use of live cloud credentials for deploy | **NOT USED** |
| Stage 5 work | **NOT STARTED** |

**Do not interpret Stage 4 as “system deployed in production.”**

## Deliverables (repository)

- `.github/workflows/ci-python.yml`
- `.github/workflows/ci-infrastructure.yml`
- `.github/workflows/ci-docker.yml`
- `.github/workflows/ci-kubernetes.yml`
- `.github/workflows/release-candidate.yml`
- `.github/workflows/cd-staging.yml`
- `scripts/ci/` (check/build/smoke, synthetic artifacts, disk/kind helpers)
- `tests/ci/`
- `docs/cicd_pipeline.md`
- This report

## Artifact strategy (Variant A)

Binary production models and UCI CSV are **not** required in Git for CI.

CI generates deterministic **synthetic** ONNX + `preprocessor.joblib` (`input_dim≈43`, version `ci-synthetic-mlp-v1`).
Production serving contract remains **dim 47** / `mlp-onnx-fp32-v1` when real stage-1 artifacts are present.

Kind smoke on CI patches ConfigMap `EXPECTED_INPUT_DIM` / `MODEL_VERSION` from the synthetic marker so readiness matches the loaded artifacts. Base overlay defaults stay production-oriented (47).

## Acceptance mapping (final)

| Criterion | Result |
| --- | --- |
| Working CI definitions (Actions YAML) | **PASS** |
| GHA Python / Docker+Trivy / Infra / K8s offline | **PASS** (runs above) |
| kind E2E on GitHub-hosted runner | **PASS** ([`45019576136`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45019576136)) |
| RC packaging (synthetic, no GitHub Release) | **PASS** ([`45020271258`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45020271258)) |
| CD staging dry-run (no cloud apply) | **PASS** ([`45020843911`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/actions/runs/45020843911)) |
| No cloud deploy / no production rollout | **PASS** (confirmed not done) |
| Production artifact parity on every CI job | **SKIP** by design when synthetic |

## Known non-critical warnings

Observed on hosted runs; **did not fail** the Stage 4 gates:

1. **Node.js 20 deprecation** notices from some GitHub Actions (actions migrating toward Node 24). Cosmetic for current SHA-pinned actions; track upstream majors later.
2. **Docker build cache save** warning / error (`tar` exit code `2`) on Buildx cache export. Image build and Trivy still **SUCCESS**; cache upload is best-effort, not a security or deploy gate.

## Stage 4 readiness

**Stage 4 CI/CD is complete and verified on GitHub Actions** for the workflows listed above at commit `86410e8`.

Ready for Stage 5 planning only after explicit technical acceptance. Cloud apply, registry publish, and production deployment remain **out of scope** until separately approved.
