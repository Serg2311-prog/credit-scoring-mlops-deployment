# BLOCK 11 — Cloud app not deployed → 11.13 Controlled Cleanup

**Branch:** `cloud-deployment`
**Decision:** cloud ML application **not deployed** (residual API Trivy HIGH, GHCR Docker Login denied despite packages token checks, time limit).
**Distroless remediation:** **not continued**.
**Security gates:** **not weakened** (no CVE ignores / Trivy skip).

Status: documentation + destroy **plan only** — operator must approve before destroy.

---

## 1. Block 11 factual results (condensed)

| Area | Result |
|------|--------|
| Terraform cloud-experiment | Applied by **operator**; remote state; MK8s 1.34; worker Ready; Calico; Metrics Server |
| Dual-SG defect | Remediated in code (rules-only + `ignore_changes`); “Nodes to master” restored |
| State migration | Operator completed; **12** standalone SG rules in state; plan exit **0** |
| Expected TF inventory | **26** state resources including **12** SG rules (confirm live before destroy) |
| App deploy to cloud | **Not** executed (no successful private GHCR publish + no kubectl apply of app) |
| Local images | Built with real ONNX FP32 + preprocessor (not synthetic CI models) |

### Trivy (CRITICAL/HIGH, gates on)

| Image | Before remediation | After remediation |
|-------|--------------------|-------------------|
| models | FAIL — 2 HIGH (OpenSSL 3.5.9-r0 → fix r2) | **PASS — 0** |
| api | FAIL — 102 (2 CRITICAL + 100 HIGH, bookworm, Fixed empty) | FAIL — **53 HIGH / 0 CRITICAL** (trixie, Fixed empty) |
| frontend | PASS | PASS (unchanged) |

### Local smoke / parity / SHA256

| Check | Result |
|-------|--------|
| `/health/ready`, `/model/info` (`mlp-onnx-fp32-v1`) | PASS |
| `/predict` | PASS (p≈0.830205) |
| ONNX parity (ORT logit → sigmoid vs `/predict`) | **PASS** abs_delta=0 |
| Protected SHA256 ×6 vs Block10 baseline | **MATCH** |

### GHCR / auth (operator-reported; cause not asserted)

| Observation | Status |
|-------------|--------|
| Repo / intended packages owner | `serg2311-prog` — repo **PRIVATE** |
| Dedicated operator PAT | Has `write:packages` (operator statement) |
| GitHub API / GHCR token endpoint | **HTTP 200** (operator statement) |
| `docker login ghcr.io` | **denied** |
| Root cause of login denial | **Not established** — do not claim SSO, ACL, or token shape without further proof |
| Extra token minting for publish | **Not** performed |

Publish blockers at abort: residual API OS HIGH (empty FixedVersion), Docker Login denied, experiment timebox.

---

## 2. Expected Terraform State (26)

Confirm with `terraform state list` before destroy. Conceptual set:

**Core / data (14 without full rule set historically; post-migration total 26):**

- `terraform_data.quota_guard`
- `module.network.terraform_data.cidr_unique`
- `module.network.yandex_vpc_network.this`
- `module.network.yandex_vpc_subnet.this["a"]`
- `module.network.yandex_vpc_security_group.k8s_master`
- `module.network.yandex_vpc_security_group.k8s_nodes`
- `module.iam.yandex_iam_service_account.k8s_cluster`
- `module.iam.yandex_iam_service_account.k8s_nodes`
- `module.iam.yandex_resourcemanager_folder_iam_member.k8s_cluster["k8s.clusters.agent"]`
- `module.iam.yandex_resourcemanager_folder_iam_member.k8s_cluster["vpc.publicAdmin"]`
- `module.kubernetes.terraform_data.iam_ready`
- `module.kubernetes.terraform_data.sg_rules_ready` *(if present in live state)*
- `module.kubernetes.yandex_kubernetes_cluster.this`
- `module.kubernetes.yandex_kubernetes_node_group.cpu`

**12 SG rules:**

- `…master_self`, `…master_lb_healthchecks`, `…master_api_443[0]`, `…master_api_6443[0]`, `…master_from_nodes`, `…master_egress`
- `…nodes_self`, `…nodes_from_master`, `…nodes_lb_healthchecks`, `…nodes_icmp_private`, `…nodes_pod_service_cidrs`, `…nodes_egress`

If live count ≠ 26, record actual list in operator notes before destroy — do not invent addresses.

---

## 3. Cleanup plan (operator-executed)

Full command checklist: **`results/block11/DESTROY_CHECKLIST.md`**.

Order:

1. Verify branch, workspace, state list (26 / 12 rules).
2. Confirm no app K8s leftovers.
3. Operator approval → `terraform plan -destroy` / `apply`.
4. Verify no MK8s / VMs / disks / IPs / `cs-exp-*` VPC|subnet|SG|SA; **keep default VPC/subnets**.
5. Wipe tfstate bucket **versions + delete markers**, then delete bucket + tfstate SA/keys.
6. `docker logout ghcr.io`, revoke temp PAT, clear shell AWS/GHCR env.
7. Billing check.

---

## 4. Operator destroy approval

Await explicit operator approval before any destroy/delete.

Until then: no `terraform destroy`/`apply`, no bucket/SA deletion.
