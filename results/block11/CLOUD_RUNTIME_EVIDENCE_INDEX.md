# CLOUD_RUNTIME_EVIDENCE_INDEX — Block 11

Pointers only — avoid duplicating large evidence blobs.

## Infrastructure (CLOUD_INFRA → DESTROY)

| Evidence | File | Result |
|----------|------|--------|
| Capacity / sizing | `RESOURCE_CAPACITY_REPORT.md`, `COST_ESTIMATE.md` | Planning + rates |
| Terraform audit | `TERRAFORM_AUDIT.md` | PASS with remediation notes |
| Remote state bootstrap | `REMOTE_STATE_BOOTSTRAP.md` | Historical; bucket later deleted |
| Runtime verification | `CLOUD_RUNTIME_VERIFICATION.md` | Live then destroy completed |
| Dual-SG remediation | `RUNTIME_REMEDIATION_REPORT.md` | Fixed in code; 12 standalone rules |
| Destroy / abort | `DESTROY_CHECKLIST.md`, `BLOCK11_ABORT_AND_CLEANUP.md` | Operator destroy; 26 TF addresses |
| Cleanup closeout | `FINAL_CLEANUP_REPORT.md` | Destroy verified |

## Application (local only; cloud ABORT)

| Evidence | File | Result |
|----------|------|--------|
| Image build / Trivy (historical + delivery) | `IMAGE_BUILD_REPORT.md` | Experiment trixie residual; delivery PASS |
| App verification JSON | `application_verification_summary.json` | smoke/parity/SHA PASS |

## Closure

| Evidence | File |
|----------|------|
| Final experiment report | `FINAL_CLOUD_EXPERIMENT_REPORT.md` |
| Cost (confirmed 2026-11-26) | `FINAL_COST_REPORT.md` |
| Security | `FINAL_SECURITY_REVIEW.md` |
| Regression | `FINAL_REGRESSION_REPORT.md` |
| Machine summary | `final_verification_summary.json` |

## Explicitly not evidenced

- Cloud inference / cloud HPA runtime / NetworkPolicy enforcement tests
- Cloud monitoring stack / rolling update / rollback
- Guarantee of zero future billing accruals
- Full local credential wipe (shell / kubeconfig / docker login) unless operator attaches evidence
