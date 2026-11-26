# FINAL_SECURITY_REVIEW — Block 11.14

## Repository hygiene

| Check | Result |
|-------|--------|
| Terraform state / backups tracked? | NO (gitignored; present locally) |
| Plan binaries / raw sensitive plan JSON tracked? | NO |
| Real `backend.hcl` / `terraform.tfvars` tracked? | NO (gitignored; present locally) |
| Access/secret keys / PAT / IAM tokens in tracked files? | NO (placeholders only in docs) |
| kubeconfig / Docker creds tracked? | NO |
| Protected models / instructor model pack ZIP tracked? | NO (policy unchanged) |
| Historical Block 7/8 evidence mutated? | NO — git trees match Block 10 baseline |
| Trivy ignore rules added / gates weakened? | NO |

## Terraform security posture

| Control | Result |
|---------|--------|
| Kubernetes API `0.0.0.0/0` | Rejected by validation (`c != "0.0.0.0/0"` + prefix ≥1) |
| Mixed inline + standalone SG rules | Removed — rules-only + `ignore_changes` on shells |
| IAM broad admin/editor roles | Avoided in module (existing tests) |
| NodePort public | Disabled by default |
| Remote state examples | Examples only; live bucket destroyed |

## Container scanning

| Image | Experiment (11.10, historical) | Delivery / merge-prep (11.15) |
|-------|--------------------------------|-------------------------------|
| models | PASS after openssl bump | **PASS** (included in delivery) |
| frontend | PASS | **PASS** |
| api | FAIL residual 53 HIGH / 0 CRITICAL on **trixie** experiment image | **PASS** on restored `main` bookworm `Dockerfile.api` (CI gate: CRITICAL/HIGH + ignore-unfixed) |

Experimental trixie API remediation is **not** in the final delivery. Do **not** treat the historical 53 HIGH as a current delivery blocker. Merge-prep Trivy on restored bookworm API + models + frontend: **PASS** (CRITICAL/HIGH + `ignore-unfixed`). Details: `IMAGE_BUILD_REPORT.md`.

## GHCR

- PAT had `write:packages`; API/token HTTP 200; `docker login` denied; root cause **not established**; **no push**.

## Evidence sanitization

Block 11 docs use placeholders (`<FOLDER_ID>`, `<secret>`) for credentials. No client PII. Absolute personal paths not required in published evidence summaries.
