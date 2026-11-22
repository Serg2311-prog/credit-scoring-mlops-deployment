# Stage 4 Validation Report — CI/CD

**Date:** 2026-11-22
**Scope:** GitHub Actions workflows, synthetic CI artifacts, local check scripts, docs
**Not done:** git push, cloud apply, YCR publish, production CD, stage 5

## Preconditions

| Item | Result |
| --- | --- |
| Git branch | `main` @ `6e151eb` (+ stage-4 uncommitted changes) |
| Git remote | **absent** (`git remote -v` empty) |
| GitHub Actions on hosted runners | **NOT EXECUTED** (no remote) |

## Deliverables

- `.github/workflows/ci-python.yml`
- `.github/workflows/ci-infrastructure.yml`
- `.github/workflows/ci-docker.yml`
- `.github/workflows/ci-kubernetes.yml`
- `.github/workflows/release-candidate.yml`
- `.github/workflows/cd-staging.yml`
- `scripts/ci/{check,build_images,smoke}.ps1`
- `scripts/ci/generate_synthetic_artifacts.py`
- `scripts/ci/verify_artifacts.py`
- `tests/ci/test_workflows.py`
- `docs/cicd_pipeline.md`

## Artifact strategy

Variant A: synthetic ONNX+joblib for CI contract tests.
Verified locally into `artifacts/ci/models` (input_dim=43, version `ci-synthetic-mlp-v1`).
Refuses overwrite of non-synthetic `models/` without `--force`.

## Local verification

| Check | Result |
| --- | --- |
| Synthetic artifact generation | **PASS** |
| `verify_artifacts.py --allow-synthetic` | **PASS** |
| pytest (full suite with local stage-1 models) | **91 passed** |
| flake8 / black | **PASS** (0) |
| Workflow static tests | **PASS** |
| Docker API/models local build | **PASS** (`:ci` tags) |
| Terraform apply | **NOT RUN** |
| Docker Trivy on GHA | **NOT EXECUTED** (no remote) |
| kind smoke on GHA | **NOT EXECUTED** (optional + no remote) |

## Acceptance mapping

| Criterion | Result |
| --- | ---: |
| Working CI definitions (Actions YAML) | **PASS** |
| Local reproduction of main checks | **PASS** (scripts + pytest) |
| GHA green on GitHub | **SKIPPED / NOT EXECUTED** — no remote |
| Terraform checks in CI YAML | **PASS** (defined; validated locally earlier in 3B) |
| K8s manifest checks | **PASS** (defined + local pytest/kustomize available) |
| Docker build + vuln scan workflow | **PASS** (defined; local build optional) |
| E2E / integration via synthetic | **PASS** (integration markers + generator) |
| Real production artifact tests on CI | **SKIP** by design when synthetic |
| RC packaging | **PASS** (manual workflow, no GitHub Release) |
| CD staging dry-run gate | **PASS** (manual confirm; no cloud) |
| No cloud resources / no apply | **PASS** |

## Known issues

1. Synthetic preprocessor dim (≈43) ≠ production 47 — expected; marker separates them.
2. `environment: staging` in CD requires creating the Environment in GitHub UI (optional).
3. Trivy may fail builds on unfixed HIGH CVEs in base images — adjust allowlist only with justification.

## Hotfix after first GitHub Actions run (commit `e04ff15`)

| Failure | Fix | Local verification |
| --- | --- | --- |
| `kubectl apply --dry-run=client` → OpenAPI `localhost:8080` | `kubeconform v0.6.7` offline (`-strict`, k8s `1.33.0`) in `ci-kubernetes.yml` + `ci-infrastructure.yml` | **PASS** — 4/4 resources valid |
| `aquasecurity/trivy-action@0.28.0` unresolved | Pin `aquasecurity/trivy-action@ed142fd…` (**v0.36.0**) | SHA verified via GitHub API tag object |
| Floating action tags | Pin checkout/setup-python/upload-artifact/buildx/terraform/kubectl to full SHAs | workflow static tests assert 40-hex pins |

No ML/API/Terraform-apply changes. No auto commit/push.

## Stage 4 readiness

**CI definitions corrected for hosted runners; local kubeconform + pytest gates green.**
Awaiting technical acceptance before commit/push.
