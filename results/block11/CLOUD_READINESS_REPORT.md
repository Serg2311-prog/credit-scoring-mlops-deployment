# CLOUD_READINESS_REPORT — Block 11.5 → 11.7.1

> **Supersession (11.14/11.15):** cloud infra was later migrated, runtime-verified, then **destroyed**; cloud app closed as `ABORT_CLOUD_APP`. Authoritative closeout: [`FINAL_CLOUD_EXPERIMENT_REPORT.md`](FINAL_CLOUD_EXPERIMENT_REPORT.md). This file remains a historical readiness snapshot.

**Final status (11.9.1):** `READY_FOR_STATE_MIGRATION`
**Supersedes:** `READY_FOR_REMOTE_STATE_BOOTSTRAP` (11.7.1) after operator completed bootstrap + apply.
**Not assigned (at 11.9.1):** full app `DEPLOYED` (later `ABORT_CLOUD_APP`)
**Branch:** `cloud-deployment`
**Date:** 2026-11-26

## Executive verdict

Cloud experiment infrastructure is **live** (Remote State, Apply, MK8s 1.34.1, Ready worker, Calico, Metrics Server). Block 11.9.1 fixed dual-managed SG rules in code and documented import-first state migration. **Do not** blind-apply until migration plan passes a no-destroy plan. ML app deploy remains NOT_EXECUTED.

## Problems found

1. **Staging defaults ≠ experiment target** — 2c/4g preemptible, K8s 1.30, extras always on.
2. **Compute quota saturation** — worker 4/16/64 fills confirmed quotas; default node surge would fail or need second VM.
3. **Staging K8s 1.30 obsolete** vs REGULAR channel 1.32–1.35 (experiment uses 1.34).
4. **Master RUB rates** not extractable as text from official pricing page (image) — estimates use secondary digest.
5. **State locking** on Yandex Object Storage **NOT_VERIFIED**.
6. **kubeconform** not installed — SKIPPED.
7. **Public IP / MK8s cluster quotas** not in operator’s confirmed list — must verify in console before apply.
8. **GHCR auth** for private pulls not wired in Terraform — needs manual `imagePullSecret`.
9. **Full Loki+Alloy+Alertmanager** with Prom/Grafana/API is tight — sequential / optional deferral.
10. **Models** are local/gitignored (expected); must not publish to public registry.

## Changes made

### 11.5 (baseline prep)
| Change | Why |
|--------|-----|
| New `cloud-experiment/` | Isolated experiment config |
| deploy_policy + upgrade knobs | No surge VM; freeze upgrades |
| Optional registry/storage/monitoring | Minimize paid surface |

### 11.7.1 (hardening)
| Change | Why |
|--------|-----|
| `master_min_resource_preset_id` (null default; exp=`s-c2-m8`) | Explicit minimum master profile (not a max) |
| Optional ml-reader / registry-pusher SAs + gated YCR/logging roles | Least privilege when YCR/logging/LB off |
| SG: API 443+6443, LB healthchecks, ICMP, pod/service CIDRs | Align with YC MK8s SG docs; still no SSH/NodePort |
| Admin CIDR validation `/1–/32` IPv4 | Reject `/0` and empty/invalid |
| `REMOTE_STATE_BOOTSTRAP.md` + gitignore tighten | Safe bootstrap via Bucket Policy (no folder IAM) |

**Production / staging behavior:** unchanged (new knobs default to prior behavior).

## Planned resources (minimal apply)

- VPC + subnet `10.40.0.0/24` (ru-central1-a)
- Security groups (master API CIDR-restricted; no SSH/NodePort public)
- IAM service accounts + role bindings
- MK8s zonal REGULAR **1.34**, Calico, public master
- 1× CPU node group: standard-v3, 4c/16g/100%/64GB SSD, non-preemptible, NAT, `max_expansion=0`
- **Not** created by default: YCR, artifacts bucket, KMS, Cloud Logging, GPU NG, LB

## Confirmed quotas

| Quota | Value | Fit |
|-------|-------|-----|
| vCPU | 4 | Worker uses 4; master typically separate — **confirm** |
| RAM | 16 GB | Worker uses 16 |
| SSD | 64 GiB | Worker boot 64 |
| GPU | none | Locked off |

## Cost (minimal)

≈ **19.2 ₽/h** → **≈ 77 ₽ / 4h** (see `COST_ESTIMATE.md`). Within 500 ₽ cap.

## Test results (local) — 11.7.1 re-run

| Check | Result |
|-------|--------|
| terraform fmt -check -recursive | PASS |
| terraform init -backend=false + validate (stg/prod/exp) | PASS |
| terraform test (kubernetes mock, 4 runs) | PASS (incl. master preset) |
| git diff --check | PASS |
| gitignore (state/backup/tfplan/credentials) | PASS |
| Protected SHA256 ×6 | MATCH |
| Remote state bootstrap / apply (by operator, after this checklist era) | **EXECUTED** then later **DESTROYED** — see final Block 11 reports |

## Risks

- Node replace with `max_expansion=0` → brief capacity loss.
- Private GHCR pull failure blocks deploy.
- Unverified public-IP quota.
- Accidental enable of LB/YCR/logging increases burn rate.
- Billing alerts do not stop resources.
- Parallel terraform without lock → state corruption risk.

## Blockers

**None hard-blocking** for `terraform plan` preparation. Soft blockers before apply:

1. Operator must supply admin CIDR + tfvars (gitignored).
2. Confirm public IP + MK8s quotas in console.
3. Prepare GHCR pull secret + image digests with real ONNX.
4. Explicit approval for plan/apply.

## Changed files

```
infra/terraform/modules/kubernetes/main.tf
infra/terraform/modules/kubernetes/variables.tf
infra/terraform/environments/cloud-experiment/* (new)
infra/terraform/README.md
results/block11/CLOUD_READINESS_REPORT.md
results/block11/TERRAFORM_AUDIT.md
results/block11/COST_ESTIMATE.md
results/block11/RESOURCE_CAPACITY_REPORT.md
results/block11/DEPLOYMENT_PLAN.md
results/block11/DESTROY_CHECKLIST.md
results/block11/verification_summary.json
```

## Exact next-stage commands (after approval only)

Follow **`results/block11/REMOTE_STATE_BOOTSTRAP.md`** in full, then:

```powershell
cd infra/terraform/environments/cloud-experiment
# terraform.tfvars from example (admin CIDR /32, gitignored)
# backend.tf + backend.hcl from examples (gitignored); AWS_* via env only
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
# STOP — review: master min preset s-c2-m8, 1 worker, no GPU, no ml-reader/pusher SAs
# terraform apply tfplan   # separate approval
```

---

**STOP.** No cloud mutations. Await operator approval for Remote State Bootstrap.
