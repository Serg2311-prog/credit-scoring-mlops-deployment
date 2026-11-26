# FINAL_CLOUD_EXPERIMENT_REPORT — Block 11.14

**Branch:** `cloud-deployment`
**Closure status (11.14):** `READY_WITH_DOCUMENTED_LIMITATIONS`
**Merge prep (11.15):** `READY_FOR_FINAL_MERGE` — `Dockerfile.api` restored to `main`; Trivy gate PASS; see `MERGE_READINESS_REPORT.md`
**Date:** 2026-11-26

## 1. Verdict

Cloud infrastructure experiment in Yandex Cloud was **executed, runtime-verified, and destroyed**. Cloud application deployment was **aborted** (`ABORT_CLOUD_APP`). No new cloud resources remain from the experiment. Project documentation and merge classification updated accordingly. No git commit/push/merge performed by the agent.

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
| Remote Terraform State in private Object Storage (versioning) | Cloud infra runtime verified (later destroyed) |
| Managed Kubernetes 1.34, channel REGULAR | Cloud infra runtime verified |
| CPU worker 4 vCPU / 16 GB / SSD 64 GB | Cloud infra runtime verified |
| Node Ready, kubelet v1.34.1 | Cloud infra runtime verified |
| Cluster RUNNING / HEALTHY | Cloud infra runtime verified |
| Calico, CoreDNS, Metrics Server, kube-proxy, CSI Running | Cloud infra runtime verified |
| API `/readyz` → `ok` on :6443 | Cloud infra runtime verified |
| Intermittent TLS handshake timeout | Observed; **root cause not established** |
| 12 SG rules migrated inline → standalone resources | Cloud infra runtime verified |
| Stale state binding fixed | Cloud infra runtime verified |
| Pod/Service CIDR order conflict resolved | Cloud infra runtime verified |
| Pre-guard plan: 1 add / 0 change / 0 destroy | Cloud infra runtime verified |
| Terraform Destroy by operator | Destroy verified |
| YC CLI: no experimental K8s/NG/VM/IG/disks/IPs/VPC/subnets/SGs | Destroy verified |
| Default VPC + 4 default subnets + default SG preserved | Destroy verified |
| State bucket deleted; static access key deleted (empty list) | Destroy verified |
| Final SA delete / GitHub PAT revoke / local creds wipe | **Not asserted** without operator evidence |

## 4. Application deployment — confirmed facts

| Fact | Status |
|------|--------|
| Cloud app deployed | **No** — ABORT_CLOUD_APP |
| Local API / models / frontend images built | Locally runtime verified |
| Real protected ONNX + preprocessor (not synthetic CI) | Locally runtime verified |
| Smoke test | PASS |
| ONNX parity | PASS (probability 0.830205; delta 0) |
| Protected SHA256 ×6 | MATCH |
| Trivy models | PASS after remediation |
| Trivy frontend | PASS |
| Trivy API | 53 HIGH / 0 CRITICAL after remediation (Debian OS; FixedVersion empty) |
| Remaining HIGH “impossible to fix” | **Not claimed** — unfinished within experiment |
| GHCR PAT `write:packages` | Operator-confirmed |
| GitHub API / GHCR token endpoint HTTP 200 | Observed |
| `docker login ghcr.io` | denied; **root cause not established** |
| Image push | Not performed |
| Security gates weakened | **No** |
| Cloud inference / HPA / NP enforcement / monitoring / rolling / rollback | **Not verified** |
| Calico present ⇒ NetworkPolicy enforcement | **False** — not claimed |

## 5. Financial (preliminary)

See `FINAL_COST_REPORT.md`. Displayed grant consumption **50 RUB** of **4000 RUB** is UI preliminary only — not final billing.

## 6. Outcomes vs Block 10

| Topic | Block 10 | Block 11.14 |
|-------|----------|-------------|
| Terraform apply | NOT_EXECUTED | Executed then destroyed |
| Remote state live | Not verified | Verified then bucket deleted |
| MK8s runtime | Hypothetical | Verified then destroyed |
| Cloud app | Not executed | ABORT after local build/scan |
| Score most likely | 49/50 | **49/50** (infra already at max; app/HPA gaps remain) |

## 7. Reports index

- `CLOUD_RUNTIME_EVIDENCE_INDEX.md`
- `FINAL_CLEANUP_REPORT.md`
- `FINAL_COST_REPORT.md`
- `FINAL_SECURITY_REVIEW.md`
- `FINAL_PROJECT_SCORECARD.md`
- `FINAL_REGRESSION_REPORT.md`
- `DOCUMENTATION_RECONCILIATION_REPORT.md`
- `MERGE_READINESS_REPORT.md`
- `final_verification_summary.json`
