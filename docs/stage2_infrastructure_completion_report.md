# Stage 2 / Block 6 — Cloud Infrastructure Completion Report

**Date:** 2026-11-24

**HEAD baseline:** `2000331`

**Cloud `terraform apply` / destroy / paid resources:** **NOT_EXECUTED**

**AUTO_STAGING_ENABLED:** not enabled

## Status legend

| Status | Meaning |
| --- | --- |
| IMPLEMENTED | IaC / docs present |
| VERIFIED_STATIC | fmt/validate/tests without cloud |
| VERIFIED_LOCAL | Ran on this laptop |
| VERIFIED_HOSTED | GitHub Actions |
| VERIFIED_CLOUD | Real Yandex resources |
| NOT_EXECUTED | Policy / no credentials |
| BLOCKED | Attempted but unsafe / impossible here |

## 1. TZ requirements (Stage 2, 7 pts)

| Requirement | Mandatory | After Block 6 | Verification |
| --- | --- | --- | --- |
| Terraform on Yandex Cloud | Yes | Provider `~> 0.250`, modules | VERIFIED_STATIC |
| Modules VPC / K8s / Storage / Monitoring | Yes | + IAM, registry | VERIFIED_STATIC |
| Managed Kubernetes | Yes | `yandex_kubernetes_cluster` + CALICO | VERIFIED_STATIC |
| CPU **and** GPU node groups | Yes | CPU always; GPU `count` gated `enable_gpu_node_group=false` | IMPLEMENTED; GPU cloud **NOT_EXECUTED** |
| Security groups + network policy | Yes | SG module + `network_policy_provider=CALICO` + K8s NP manifests | SG/NP static VERIFIED; NP traffic **BLOCKED** (kindnet + 736 MB free RAM) |
| Object Storage | Yes | private bucket + KMS + versioning | VERIFIED_STATIC |
| Remote state in Object Storage | Yes | `backend.tf.example` + bootstrap docs | configured example; live remote **NOT_EXECUTED** |
| Staging / production | Practice | Separate CIDRs, keys, defaults | VERIFIED_STATIC |
| Monitoring | Yes | Cloud Logging group; metrics via Stage 5 Prometheus notes | VERIFIED_STATIC (logs) |

## 2. Gaps found → fixes

| Gap | Fix |
| --- | --- |
| GPU node group missing | Added `yandex_kubernetes_node_group.gpu` with schema attrs `gpus`, `gpu_settings`, `node_labels`, `node_taints`; default **off** |
| Provider pin drift (`>=0.140` vs `~>0.250`) | All modules `~> 0.250` |
| Remote state lock docs weak | Expanded `backend.tf.example` (no DynamoDB lock; serialize applies) |
| Docs claimed `acl=private` | Aligned to `anonymous_access_flags` (no deprecated ACL) |
| stage label `3b` | Renamed to `stage = "2"` |
| CI kubeconform only local | CI validates local + staging + production overlays |
| NP enforcement unverified | Attempted; **BLOCKED** (kindnet + insufficient RAM for Calico sidecar / second cluster) |

## 3. Architecture (after Block 6)

```text
environments/{staging|production}
  network → VPC + subnet + master/nodes SG
  iam → least-privilege SAs
  monitoring → yandex_logging_group
  registry → container registry
  storage → private bucket + optional KMS
  kubernetes → MK8s (CALICO)
                 ├ node_group.cpu (labels; optional auto_scale)
                 └ node_group.gpu (count=0 unless enable_gpu_node_group)
```

GPU example workload (not applied): `k8s/examples/gpu-workload/`.

## 4. Validation results

| Check | Result |
| --- | --- |
| `terraform fmt -recursive -check` | PASS |
| staging/production `init -backend=false` + `validate` | PASS |
| `terraform test` (kubernetes mock_provider) | **3 passed** (Block 6.1) |
| Provider schema (GPU attrs) | Inspected locally |
| `kubectl kustomize` local/staging/production | PASS |
| NetworkPolicy traffic probes | **BLOCKED** (kindnet + low RAM) |
| `terraform apply` / live remote | **NOT_EXECUTED** |

> **Historical note:** this Stage 2 / Block 6 completion predates the Block 11 cloud-experiment apply→destroy. Current cloud status: [`results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md).

## 5. Remote state honesty

| Aspect | Status |
| --- | --- |
| Example backend S3→Yandex | IMPLEMENTED |
| Separate staging/prod keys | Documented |
| Live bucket + init -migrate-state | NOT_EXECUTED |
| Native distributed lock | **Unavailable** on Yandex S3 API (documented) |

## 6. NetworkPolicy

- Manifests: default-deny + allow frontend/API — render OK.
- Cloud path: MK8s `network_policy_provider = CALICO`.
- Local kind: kindnet → no enforcement; Calico install **BLOCKED** (RAM).

## 7. Production artifacts

Unchanged hashes recorded in final Block 6 report (acceptance section).
