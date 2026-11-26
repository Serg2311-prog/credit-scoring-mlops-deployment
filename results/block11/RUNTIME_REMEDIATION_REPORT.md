# RUNTIME_REMEDIATION_REPORT — Block 11.9.1

> Later closeout: SG migration completed in experiment; infra destroyed; app `ABORT_CLOUD_APP`. See [`FINAL_CLOUD_EXPERIMENT_REPORT.md`](FINAL_CLOUD_EXPERIMENT_REPORT.md).

**Branch:** `cloud-deployment`
**Status (at 11.9.1):** `READY_FOR_STATE_MIGRATION`
**Cloud mutations this block:** none (code + docs only)
**terraform apply/destroy/state mv|rm|import (this block, by agent):** **NOT_EXECUTED**

## Confirmed runtime (operator + read-only checks)

| Fact | Level | Result |
|------|-------|--------|
| Terraform Apply (prior) | Real cloud infra | 2 added, 4 changed, 0 destroyed |
| Remote State | Real cloud infra | 14 managed resources |
| Managed Kubernetes | Real cloud infra | v1.34.x, RUNNING/HEALTHY, REGULAR, master min preset `s-c2-m8` |
| CPU worker | Real cloud infra | standard-v3, 4 vCPU / 16 GiB / 64 GiB network-ssd, NAT, Node Group RUNNING |
| Worker registration | Ops cloud | Ready after manual SG rule restore |
| Calico | Ops cloud | `network_policy.provider=CALICO`; calico-node/typha Running (when API reachable) |
| Metrics Server | Ops cloud | 2 replicas Running; metrics API returned node usage (~69–74m CPU class, ~1.3 Gi memory class) |
| ML app in cloud | Real cloud app | **NOT_EXECUTED** |

## Defect — root cause

Terraform **dual-managed** Master Security Group rules:

1. Inline `ingress` / `egress` blocks on `yandex_vpc_security_group.k8s_master`
2. Separate `yandex_vpc_security_group_rule.master_from_nodes` (“Nodes to master”)

On Recovery Apply, the provider reconciled the SG resource to **only** its inline rules and **deleted** the separately managed “Nodes to master” rule. Worker lost master connectivity → `NOT_CONNECTED`. Manual recreate of the rule restored Ready.

This is a known class of Yandex VPC provider footgun: **do not mix** inline SG rules and `yandex_vpc_security_group_rule` on the same security group.

## Code fix (repo only)

`infra/terraform/modules/network/main.tf` now:

- Creates Master/Nodes SGs as **empty shells** (metadata only)
- Manages **all** rules exclusively via `yandex_vpc_security_group_rule`
- Preserves no-SSH / no-NodePort-by-default / no `0.0.0.0/0` API posture
- Avoids circular `depends_on` between the two SG resources (cross-SG refs only in rule resources)

Pod/Service CIDR defaults corrected to match live `ip_allocation_policy`:

| | Live cloud | Previous TF default | New TF default |
|-|------------|---------------------|----------------|
| Pod / cluster CIDR | `10.112.0.0/16` | `10.96.0.0/16` (misnamed) | `10.112.0.0/16` |
| Service CIDR | `10.96.0.0/16` | `10.112.0.0/16` (misnamed) | `10.96.0.0/16` |

Both ranges were already allowed together on the node SG, so runtime allowlist remained functionally covering both; naming is now correct for future diffs.

## What was NOT done

- No SG/IAM/VPC/K8s changes in the cloud
- No state migration in this remediation step (migration executed later in experiment; see `BLOCK11_ABORT_AND_CLEANUP.md` for 26-address / 12-rule inventory)
- No image publish / app deploy
- No model changes

## TLS handshake timeouts (read-only)

Intermittent `net/http: TLS handshake timeout` observed on `kubectl` against the public API (some calls ~11–22s fail, others ~1.3s succeed). TLS verification was **not** disabled. Likely contributors: public endpoint path, admin CIDR path, client network instability — **not** treated as fixed. Retry-safe read-only ops still succeed periodically (namespaces list, metrics API, kube-system pod list).

## Local gates (this block)

| Gate | Result |
|------|--------|
| terraform fmt -check | PASS |
| validate staging/production/cloud-experiment | PASS |
| kubernetes mock tests (4) | PASS |
| git diff --check | PASS |
| Protected SHA256 ×6 | MATCH |
| state/secrets not tracked | PASS |

## Block 11.9.2 — Safe migration hardening

| Item | Result |
|------|--------|
| Mandatory `terraform state pull` backup before rm/import | Encoded in `scripts/block11/Invoke-SgStateMigration.ps1` |
| Manual JSON edit / `state push` | **Removed** from staff path |
| Import ID (provider 0.250.0) | `<security_group_id>:<rule_id>` (`resourceid.Deconstruct`) |
| Empty SG + separate rules | Confirmed incompatible with inline; `lifecycle.ignore_changes = [ingress, egress]` |
| SG descriptions | Restored to original strings (no unnecessary update) |
| K8s depends_on SG rules | `security_group_dependency_ids` → create/destroy order |
| Idempotent script | Maps 12 live rules by description; skip/repair/import; plan gate |
| Agent executed migration? | **No** |

## Next

Operator runs `scripts/block11/Invoke-SgStateMigration.ps1` with plan gate PASS and separate approval. Post-migration inventory: `BLOCK11_ABORT_AND_CLEANUP.md`.
