# Block 6.1 — Infrastructure Final Acceptance Notes

**Date:** 2026-11-24

**Baseline:** Block 6 on top of `2000331`

**terraform apply / live remote / GHCR / AUTO_STAGING:** NOT_EXECUTED

## 1. Remote state ("example-only")

| Item | Status |
| --- | --- |
| Meaning | Config + bootstrap docs exist; **no** live bucket, **no** committed `backend.tf`, **no** `init` against remote |
| `backend.tf.example` | Staging + production (partial/inline patterns) |
| `backend.hcl.example` | For `terraform init -backend-config=backend.hcl` |
| Distinct keys | `.../staging/terraform.tfstate` vs `.../production/terraform.tfstate` |
| Versioning / encryption | Documented for operator bootstrap (bucket settings) |
| IAM | Dedicated SA, keys via env — never Git |
| `use_lockfile` | **Not enabled** — Yandex compatibility **NOT_VERIFIED** (HashiCorp: non-AWS S3 best-effort) |
| Safe ops without lock | Single operator / CI concurrency; no parallel apply |

## 2. Native Terraform tests vs Python

| Suite | Result |
| --- | --- |
| `terraform test` (module kubernetes, mock_provider, `command=plan`) | **3 passed** (GPU off / autoscaling / GPU on) |
| Python `tests/terraform` | Static layout/security (separate) |

## 3. GPU (schema-verified locally)

Present in IaC: `platform_id`, `resources.gpus/cores/memory`, `gpu_settings.gpu_environment`, `node_labels`, `node_taints`, `allocation_policy.location`, `scale_policy`.
Default: `enable_gpu_node_group=false`.
Workload example: nodeSelector + tolerations + `nvidia.com/gpu` — needs NVIDIA device plugin / drivers in real MK8s (**NOT_EXECUTED**).

## 4. Monitoring vs ТЗ

Cloud Logging module + Stage 5 Prometheus/Grafana satisfy modular «Monitoring» without extra paid Yandex Monitoring resources. No mandatory gap requiring new paid services.

## 5. NetworkPolicy

- TF default `network_policy_provider = CALICO` (asserted in native test).
- K8s NP manifests: standard `networking.k8s.io/v1` (Calico-compatible).
- Local traffic enforcement: **BLOCKED** (kindnet + low RAM) — unchanged.
