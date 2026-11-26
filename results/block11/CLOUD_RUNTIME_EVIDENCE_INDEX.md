# CLOUD_RUNTIME_EVIDENCE_INDEX — Block 11.14

Pointers only — avoid duplicating large evidence blobs.

## Infrastructure (CLOUD_INFRA → DESTROY)

| Evidence | File | Result |
|----------|------|--------|
| Readiness / capacity | `CLOUD_READINESS_REPORT.md`, `RESOURCE_CAPACITY_REPORT.md` | PASS (historical live) |
| Terraform audit | `TERRAFORM_AUDIT.md` | PASS with remediation notes |
| Remote state bootstrap | `REMOTE_STATE_BOOTSTRAP.md` | Historical; bucket later deleted |
| Runtime verification | `CLOUD_RUNTIME_VERIFICATION.md` | Updated: destroy completed |
| Dual-SG remediation | `RUNTIME_REMEDIATION_REPORT.md` | Fixed in code |
| SG state migration | `STATE_MIGRATION_PLAN.md` | Migration executed in experiment |
| Destroy checklist / abort | `DESTROY_CHECKLIST.md`, `BLOCK11_ABORT_AND_CLEANUP.md` | Operator destroy |
| Cleanup closeout | `FINAL_CLEANUP_REPORT.md` | Destroy verified |

## Application (local only; cloud ABORT)

| Evidence | File | Result |
|----------|------|--------|
| Preflight | `APP_DEPLOYMENT_PREFLIGHT.md` | PASS local gates |
| Image build / Trivy | `IMAGE_BUILD_REPORT.md` | models/frontend PASS; API residual HIGH |
| STOP GATE 1 | `BLOCK11_10_STOP_GATE_1.md` | STOP then ABORT |
| App verification JSON | `application_verification_summary.json` | smoke/parity/SHA PASS |
| Deploy plan (not executed) | `DEPLOYMENT_PLAN.md` | Stages C–D cancelled |

## Closure

| Evidence | File |
|----------|------|
| Final experiment report | `FINAL_CLOUD_EXPERIMENT_REPORT.md` |
| Cost | `FINAL_COST_REPORT.md` |
| Security | `FINAL_SECURITY_REVIEW.md` |
| Scorecard | `FINAL_PROJECT_SCORECARD.md` |
| Regression | `FINAL_REGRESSION_REPORT.md` |
| Docs reconciliation | `DOCUMENTATION_RECONCILIATION_REPORT.md` |
| Merge readiness | `MERGE_READINESS_REPORT.md` |
| Machine summary | `final_verification_summary.json` |

## Explicitly not evidenced

- Cloud inference / cloud HPA runtime / NetworkPolicy enforcement tests
- Cloud monitoring stack / rolling update / rollback
- Final billing statement / personal charge confirmation
- Final SA deletion, PAT revoke, local credential wipe (unless operator attaches evidence)
