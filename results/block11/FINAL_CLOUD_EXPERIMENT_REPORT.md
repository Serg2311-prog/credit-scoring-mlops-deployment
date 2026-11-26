# FINAL_CLOUD_EXPERIMENT_REPORT — Block 11

**Date:** 2026-11-26
**Closure:** cloud infrastructure executed → verified → destroyed; cloud application **not** deployed (`ABORT_CLOUD_APP`).

## 1. Verdict

Cloud infrastructure experiment in Yandex Cloud was **executed, runtime-verified, and destroyed**. Cloud application deployment was **aborted**. No experimental cloud resources remain. Delivery API image is restored `main` bookworm `Dockerfile.api`; merge-prep Trivy gate **PASS** (see `IMAGE_BUILD_REPORT.md`).

## 2. Verification levels used

| Level | Meaning |
|-------|---------|
| Implemented | Code/manifests present |
| Statically validated | fmt/validate/kustomize/unit |
| Locally runtime verified | Compose/kind/local smoke |
| Cloud infrastructure runtime verified | Real YC resources observed |
| Cloud application not deployed | ABORT_CLOUD_APP |
| Destroy verified | Operator YC CLI empty checks |
| Not verified | Explicitly unproven |

## 3. Cloud infrastructure — confirmed facts

| Fact | Status |
|------|--------|
| Terraform created real YC infrastructure | Cloud infra runtime verified |
| Remote Terraform State in private Object Storage (versioning) | Verified, later destroyed |
| Managed Kubernetes 1.34, channel REGULAR | Verified |
| CPU worker 4 vCPU / 16 GB / SSD 64 GB | Verified |
| Node Ready, kubelet v1.34.1 | Verified |
| Cluster RUNNING / HEALTHY | Verified |
| Calico, CoreDNS, Metrics Server, kube-proxy, CSI Running | Verified |
| API `/readyz` → `ok` on :6443 | Verified |
| Intermittent TLS handshake timeout | Observed; root cause not established |
| 12 SG rules migrated inline → standalone resources | Verified |
| Expected TF inventory ≈ **26** addresses including **12** SG rules | See `BLOCK11_ABORT_AND_CLEANUP.md` |
| Stale state binding fixed | Verified |
| Pod/Service CIDR order conflict resolved | Verified |
| Pre-guard plan: 1 add / 0 change / 0 destroy | Verified |
| Terraform Destroy by operator | Destroy verified |
| YC CLI: no experimental K8s/NG/VM/IG/disks/IPs/VPC/subnets/SGs | Destroy verified |
| Default VPC + 4 default subnets + default SG preserved | Destroy verified |
| State bucket deleted; static access key deleted | Destroy verified |
| Final SA delete / GitHub PAT revoke / local creds wipe | **Not asserted** without operator evidence (billing confirmation later cleared SA/PAT lists) |

## 4. Application deployment — confirmed facts

| Fact | Status |
|------|--------|
| Cloud app deployed | **No** — ABORT_CLOUD_APP |
| Abort reasons | Residual API Trivy HIGH on experimental trixie image; `docker login ghcr.io` denied (root cause not established); experiment timebox |
| Local API / models / frontend images built | Locally runtime verified |
| Real protected ONNX + preprocessor (not synthetic CI) | Locally runtime verified |
| Smoke / ONNX parity / SHA256 ×6 | PASS / PASS / MATCH |
| Trivy models / frontend | PASS |
| Trivy API (historical trixie experiment) | 53 HIGH / 0 CRITICAL (FixedVersion empty) |
| Trivy API (delivery bookworm, merge-prep) | **PASS** (CRITICAL/HIGH + ignore-unfixed) |
| Security gates weakened | **No** |
| Cloud inference / HPA / NP enforcement / monitoring / rolling / rollback | **Not verified** |
| Calico present ⇒ NetworkPolicy enforcement | **False** — not claimed |

## 5. Financial

Confirmed operator billing **2026-11-26**: consumption **56,34 ₽**, grant-covered **56,34 ₽**, due **0,00 ₽**.
Details: `FINAL_COST_REPORT.md`. Future accruals are **not** guaranteed absent.

## 6. Outcomes vs Block 10

| Topic | Block 10 | Block 11 |
|-------|----------|----------|
| Terraform apply | NOT_EXECUTED | Executed then destroyed |
| Remote state live | Not verified | Verified then bucket deleted |
| MK8s runtime | Hypothetical | Verified then destroyed |
| Cloud app | Not executed | ABORT after local build/scan |

## 7. Reports index

- `CLOUD_RUNTIME_EVIDENCE_INDEX.md`
- `CLOUD_RUNTIME_VERIFICATION.md`
- `BLOCK11_ABORT_AND_CLEANUP.md`
- `DESTROY_CHECKLIST.md`
- `FINAL_CLEANUP_REPORT.md`
- `FINAL_COST_REPORT.md`
- `FINAL_SECURITY_REVIEW.md`
- `FINAL_REGRESSION_REPORT.md`
- `IMAGE_BUILD_REPORT.md`
- `TERRAFORM_AUDIT.md`
- `RUNTIME_REMEDIATION_REPORT.md`
- `final_verification_summary.json`
