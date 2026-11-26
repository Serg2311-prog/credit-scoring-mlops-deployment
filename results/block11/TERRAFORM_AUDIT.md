# Terraform Audit — Block 11.5 / 11.7.1

> **Historical note:** `NOT_EXECUTED` below describes the audit *at the time of writing*. Operator later bootstrapped remote state, applied, then destroyed. Final outcome: [`FINAL_CLOUD_EXPERIMENT_REPORT.md`](FINAL_CLOUD_EXPERIMENT_REPORT.md).

**Branch:** `cloud-deployment` @ `b713f2fcc7fd4638d4464ad9395fce483a86bdad` (+ uncommitted 11.7.1 hardening)
**Provider pin:** `yandex-cloud/yandex` `0.250.0` (`~> 0.250`) — **not upgraded**.
**Apply/destroy / remote-state create (at audit time):** **NOT_EXECUTED**.

## 11.7.1 hardening delta

| Area | Change |
|------|--------|
| Master | Optional `master_min_resource_preset_id`; dynamic `scale_policy.auto_scale`; experiment `s-c2-m8` (**minimum floor**, not max) |
| IAM | Optional ml-reader / registry-pusher SAs; optional YCR puller + logging.writer; required `k8s.clusters.agent` + `vpc.publicAdmin` retained; experiment disables extras |
| Network | API 443+6443; `loadbalancer_healthchecks`; ICMP private; pod/service CIDR ingress; CIDR validation IPv4 `/1–/32`; still no SSH/NodePort/NAT GW/LB |
| Remote state | `REMOTE_STATE_BOOTSTRAP.md` — Bucket Policy (no `add-access-binding`, no folder IAM) |

## Environments

| Env | Purpose | Notes |
|-----|---------|-------|
| `staging/` | Course staging | Defaults: 2c/4g preemptible, K8s 1.30, public master off, YCR+storage+KMS+logging on |
| `production/` | Production | Untouched in Block 11.5 |
| `cloud-experiment/` | **NEW** grant experiment | Quota-locked 4c/16g/64ssd, K8s 1.34 REGULAR, GPU/autoscaling forbidden, optional paid modules off |

## Module review

### network
- VPC + single subnet; master SG: API :443 only from `k8s_api_allowed_cidrs`; no SSH.
- Nodes SG: no public SSH; NodePort off by default (`enable_nodeport_ingress=false`).
- Egress `0.0.0.0/0` on nodes (needed for GHCR/OS); NAT on worker `network_interface.nat=true`.
- Experiment CIDR `10.40.0.0/24` (avoids staging `10.20.0.0/24`).

### iam
- Cluster SA: `k8s.clusters.agent`, `vpc.publicAdmin`, registry puller, logging writer; optional `load-balancer.admin`.
- Node SA: puller + logging writer.
- Extra SAs (`ml_reader`, `registry_pusher`) created even when YCR/storage disabled — low cost (IAM free); acceptable for reuse of module.

### kubernetes
- Zonal master; `network_policy_provider=CALICO`; CPU NG `gpus=0`.
- GPU NG `count = enable_gpu_node_group ? 1 : 0` — default false; mock tests cover on/off.
- **Gap found:** default `deploy_policy` unset → platform may surge a second VM on replace → **breaks 4 vCPU quota**.
- **Fix (module):** optional `cpu_deploy_max_expansion` / `cpu_deploy_max_unavailable`; experiment sets `0` / `1`.
- **Fix (module):** `master_auto_upgrade` / `node_auto_upgrade` / `node_auto_repair` knobs; experiment freezes upgrades.
- Master size 2 vCPU / 8 GB Basic is platform default for zonal basic — not a separate Terraform resource attribute in this provider schema.

### registry / storage / monitoring
- Staging/production always create them (paid surface).
- Experiment gates via `enable_registry|storage|monitoring` (default **false**).
- Storage KMS optional; experiment uses `enable_kms_encryption=false` when storage enabled.

## Provider / API compatibility

| Check | Result |
|-------|--------|
| Provider 0.250 + resources used | Compatible (init/validate OK) |
| K8s versions on REGULAR | **1.32–1.35** (`yc managed-kubernetes list-versions`) — **1.34 available** |
| Staging default `1.30` | **stale** vs current channels (still validates; would fail live apply until bumped) |
| HPA API | `autoscaling/v2` in overlay — valid for 1.34 |
| NetworkPolicy | `networking.k8s.io/v1` — valid |
| State locking on Yandex S3 | **NOT_VERIFIED** (`use_lockfile` not enabled) |

## Quotas (confirmed by operator)

| Resource (ru-central1-a) | Confirmed | Experiment use |
|--------------------------|-----------|----------------|
| vCPU | 4 | Worker 4 (master typically **outside** Compute instance quota — confirm in console) |
| RAM | 16 GB | Worker 16 |
| SSD | 64 GiB | Worker boot 64 network-ssd |
| GPU | unavailable | GPU NG locked false |
| Public IPs / MK8s clusters / SA | **not listed by operator** | Need console check before apply (2 public IPs expected: master + node NAT) |

**Node replace:** with `max_expansion=0`, replace is disruptive (`max_unavailable=1`) — no second node; **no extra quota required**. Autoscaling and GPU creation are configuration-blocked.

## Remote state

Documented in `environments/cloud-experiment/backend.tf.example` + `backend.hcl.example`.
Bucket/keys **not created**. Separate key: `credit-scoring/cloud-experiment/terraform.tfstate`.

## Destroy completeness

All resources are Terraform-managed modules (VPC, SG, SA, IAM bindings, optional logging/registry/storage, cluster, node group). Orphans risk if:
- Manual Load Balancer / PVC / static IP created outside TF
- State backend bucket left after destroy
- Disks remain if node group destroy interrupted

See `DESTROY_CHECKLIST.md`.

## Tests

| Gate | Result |
|------|--------|
| `terraform fmt -check -recursive` | PASS |
| `init -backend=false` + `validate` (staging/production/cloud-experiment) | PASS |
| `modules/kubernetes test` (mock) | PASS |
| Live `terraform plan` against cloud | **NOT_EXECUTED** |

## Production

**No production Terraform changes.** Module variable additions are backward-compatible (defaults preserve prior behavior).

## Historical readiness snapshot (merged from CLOUD_READINESS_REPORT)

Pre-apply readiness (Block 11.5–11.7.1) noted: experiment worker fills 4 vCPU / 16 GB / 64 GiB quota; `deploy_policy.max_expansion=0`; public IP / MK8s quotas must be checked in console; state locking on Yandex Object Storage NOT_VERIFIED; experiment subnet planned as `10.40.0.0/24` (ru-central1-a). Authoritative post-destroy status: `FINAL_CLOUD_EXPERIMENT_REPORT.md`.
