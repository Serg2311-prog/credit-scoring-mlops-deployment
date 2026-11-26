# MERGE_READINESS_REPORT — Block 11.15

**Branch:** `cloud-deployment`
**HEAD / main:** `b713f2fcc7fd4638d4464ad9395fce483a86bdad` (identical tip; changes are working-tree only)
**Overall status:** **`READY_FOR_FINAL_MERGE`**

## Dockerfile.api restoration

| Check | Result |
|-------|--------|
| Restored from `main` | YES (`git checkout main -- docker/Dockerfile.api`) |
| Diff vs `main` | **empty** |
| Base image (delivery) | `python:3.12-slim-bookworm` |
| Experimental trixie change in delivery | **NO — excluded** |

Historical experiment API image (trixie) results remain in `IMAGE_BUILD_REPORT.md` / `BLOCK11_10_STOP_GATE_1.md` (53 HIGH / 0 CRITICAL without FixedVersion). That remediation is **not** part of the final delivery.

## Trivy (mandatory gate = CI)

Gate: `trivy image --exit-code 1 --severity CRITICAL,HIGH --ignore-unfixed` (matches `.github/workflows/ci-docker.yml`).

| Image | Tag | CRITICAL/HIGH (fixed) | Exit |
|-------|-----|----------------------:|-----:|
| `credit-scoring-api` | `merge-prep-1115` | 0 / 0 | **0 PASS** |
| `credit-scoring-models` | `merge-prep-1115` | 0 / 0 | **0 PASS** |
| `credit-scoring-frontend` | `merge-prep-1115` | 0 / 0 | **0 PASS** |

Fresh builds scanned; prior green CI is **not** used as proof.

## Dockerfile.models

| Check | Result |
|-------|--------|
| Alpine 3.22 + `libssl3`/`libcrypto3` ≥ 3.5.9-r2 | Present (`libssl3-3.5.9-r2`, `libcrypto3-3.5.9-r2`) |
| Real ONNX + preprocessor COPY | YES; SHA256 MATCH protected baseline |
| CI/CD compatible | YES (same Dockerfile path; Trivy gate PASS) |
| Reproducible local build | YES (`docker build -f docker/Dockerfile.models`) |

## Classification

### READY_TO_MERGE (stage these)

Modified tracked files:

- `.gitignore`
- `README.md`
- `docker/Dockerfile.models` *(not Dockerfile.api)*
- `docs/architecture/overview.md`
- `docs/cloud_cost_estimate.md`
- `docs/defense_guide.md`
- `docs/docker_deployment.md`
- `docs/evidence_index.md`
- `docs/final_project_report.md`
- `docs/quick_review.md`
- `docs/requirements_matrix.md`
- `docs/terraform_infrastructure.md`
- `infra/terraform/README.md`
- `infra/terraform/environments/production/main.tf`
- `infra/terraform/environments/staging/main.tf`
- `infra/terraform/modules/iam/{main,outputs,variables}.tf`
- `infra/terraform/modules/kubernetes/{main,variables}.tf`
- `infra/terraform/modules/kubernetes/tests/cpu_gpu.tftest.hcl`
- `infra/terraform/modules/network/{main,outputs,variables}.tf`
- `results/block10/SUBMISSION_CHECKLIST.md` (pointer only)

New:

- `infra/terraform/environments/cloud-experiment/{main,outputs,providers,variables,versions}.tf`
- `infra/terraform/environments/cloud-experiment/{backend.hcl,backend.tf,terraform.tfvars}.example`
- `infra/terraform/environments/cloud-experiment/.terraform.lock.hcl`
- `scripts/block11/{Invoke-SgStateMigration,SgPlanGate,Test-SgPlanGate}.ps1`
- `results/block11/**` (sanitized reports/JSON only)

### EXPERIMENT_ONLY (not in delivery)

- Historical trixie `Dockerfile.api` change — **reverted**; documented in Block 11 reports only

### EXCLUDE_FROM_GIT (gitignored / do not force-add)

- `cloud-experiment/backend.hcl`, `terraform.tfvars`, `backend.tf`
- `*.tfstate*`, `errored.tfstate*`
- `.terraform/`, `.migration-backup/`
- `tfplan`, `tfplan-*`
- kubeconfig, PAT, IAM tokens, access keys, protected model ZIP

## Regression (Block 11.15)

All **PASS**: pytest 236+2skip, flake8, black, TF fmt, validate×3, mock, SgPlanGate, kustomize×5, compose, workflows YAML, md links, `git diff --check`, SHA256×6 MATCH, Block7/8 trees immutable.

## main unchanged

`main` tip remains `b713f2f…`. No checkout of main for commits; only used as source for Dockerfile.api restore.

## Operator git commands (do not run until APPROVE)

See STOP GATE message / section below in chat. Agent will **not** `git add` / commit / push / merge.
