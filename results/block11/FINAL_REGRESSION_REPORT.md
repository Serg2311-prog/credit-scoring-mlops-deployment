# FINAL_REGRESSION_REPORT — Block 11.14

Local checks only. No remote Terraform backend. No apply/destroy. No retrain. No dvc.lock / registry edits.

| Check | Status | Notes |
|-------|--------|-------|
| Full pytest | **PASS** | 236 passed, 2 skipped (after restoring `0.0.0.0/0` reject + README apply wording) |
| Flake8 (`src` `tests`) | **PASS** | exit 0 |
| Black `--check` (`src` `tests`) | **PASS** | 106 files unchanged |
| Terraform fmt `-check` | **PASS** | |
| Terraform validate staging (`-backend=false`) | **PASS** | |
| Terraform validate production (`-backend=false`) | **PASS** | |
| Terraform validate cloud-experiment (`-backend=false`) | **PASS** | |
| Terraform mock tests (`modules/kubernetes`) | **PASS** | 4/4 |
| SgPlanGate unit tests | **PASS** | ALL PASS |
| Kustomize build `local` | **PASS** | |
| Kustomize build `staging` | **PASS** | |
| Kustomize build `production` | **PASS** | |
| Kustomize build `cd-demo-staging` | **PASS** | |
| Kustomize build `cd-demo-production` | **PASS** | |
| Docker Compose config | **PASS** | |
| Workflow YAML parse (9 workflows) | **PASS** | |
| `git diff --check` | **PASS** | CRLF warnings only |
| Markdown links (README/docs/block11) | **PASS** | 0 broken |
| Protected SHA256 ×6 | **PASS** | MATCH vs `results/block10/audit_baseline.json` |
| Historical Block 7/8 git trees | **PASS** | Unchanged vs baseline |
| Remote Terraform backend access | **NOT_RUN** | Bucket deleted; intentionally avoided |
| terraform apply/destroy | **NOT_RUN** | Forbidden |
| Model retrain / registry change | **NOT_RUN** | Forbidden |
| Live Trivy re-scan of images | **NOT_RUN** | Prior Block 11.10 results accepted; Docker Desktop not re-driven |
| Cloud YC live probes | **NOT_RUN** | Destroyed |

## Structure-test remediation during audit

1. Restored explicit `c != "0.0.0.0/0"` in `modules/network/variables.tf` (already enforced via prefix ≥1).
2. Restored README phrase `No \`terraform apply\`` for default staging/production path while documenting Block 11 exception.

Initial pytest before fix: 2 failed / 234 passed. After fix: **236 passed**.
