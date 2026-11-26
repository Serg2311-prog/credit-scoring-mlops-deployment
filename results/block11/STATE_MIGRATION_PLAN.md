# STATE_MIGRATION_PLAN — Block 11.9.2 (Safe)

**Status:** `READY_FOR_OPERATOR_MIGRATION` — agent DryRun **PASS**; real migration is operator-owned.
**Prior 11.9.1 draft:** superseded where it conflicted (no JSON state edit / `state push`).

### Current remote state (pre-migration)

- **14** addresses today, including already-tracked `master_from_nodes`.
- Remaining **11** rule addresses are absent → after migration expect **25** total (all 12 rules present).
- Operator shell needs `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` for the Object Storage backend (script uses `terraform state list|show|pull`).

## Goals

Align Terraform state with rules-only network module **without**:

- deleting live SG rules
- dropping Master↔Worker connectivity
- manual JSON state editing / `terraform state push`
- expanding SSH/NodePort/public API

## Provider 0.250.0 facts (verified in source)

| Topic | Finding | Source |
|-------|---------|--------|
| Inline vs separate rules | **Incompatible** — mixing causes rule conflicts / wipes | Provider schema + incident 11.9.1 |
| Empty SG (no `ingress`/`egress` blocks) | Supported: SG shell + only `yandex_vpc_security_group_rule` | Provider docs / examples |
| Mitigation without `state push` | `lifecycle { ignore_changes = [ingress, egress] }` on both SGs | `modules/network` |
| **Import ID format** | **`<security_group_id>:<rule_id>`** via `resourceid.Deconstruct` | [`resource.go` ImportState @ v0.250.0](https://github.com/yandex-cloud/terraform-provider-yandex/blob/v0.250.0/yandex/services/vpc/framework/vpc_security_group_rule/resource.go) |
| **State `id` after import** | **`rule_id` only** (not the compound import id) | Same `ImportState` / schema |

Example (placeholders only):

```text
terraform import 'module.network.yandex_vpc_security_group_rule.master_from_nodes' <sg_id>:<rule_id>
# state show id  =>  <rule_id>
```

## Live YC rule JSON (read-only)

`yc vpc security-group get <id> --format json` uses API fields:

| Field | Notes |
|-------|--------|
| `protocol_name` | Required for matching (**not** `protocol`) |
| `direction` | `INGRESS` / `EGRESS` (normalized to lower-case) |
| `ports.from_port` / `ports.to_port` | Optional; `from_port` often **omitted** when `0` |
| `cidr_blocks.v4_cidr_blocks` | Optional |
| `predefined_target` | Optional (`self_security_group`, `loadbalancer_healthchecks`) |
| `security_group_id` | Optional (cross-SG refs) |
| `description` | Exact catalog match key |

StrictMode-safe parsing: never assume optional properties exist; never invent required values.

## Mandatory backup (first mutating step)

**Before any** `terraform state rm` / `terraform import`:

1. Confirm Object Storage versioning on the state bucket.
2. Script writes **mandatory** backup via `terraform state pull` under
   `%LOCALAPPDATA%\credit-scoring-mlops\tfstate-backups\cloud-experiment\`
   (outside the git repo; **UTF-8 without BOM**).
3. Validates: file present, JSON parse, `lineage`, `serial`, SHA256 sidecar.
4. Abort if backup checks fail. Repo-path backups are refused.

## Operator commands

```powershell
cd <repo>
# 1) Unit tests (no cloud)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\block11\Test-SgPlanGate.ps1

# 2) DryRun (read-only + local backup pull; no state rm/import)
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\block11\Invoke-SgStateMigration.ps1 -DryRun

# 3) Real migration (operator only; after DryRun OK)
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\block11\Invoke-SgStateMigration.ps1
```

**There is no `-SkipPlan`.** Plan Gate is mandatory after mutation.

## Script behaviour

1. **Preflight:** `terraform` + `yc`; **workspace must be `default`**; backend/path must target **cloud-experiment**; `state list`; required addresses; **cluster + node-group IDs from Terraform state** (not “first cluster”); SG IDs from state; cluster RUNNING/HEALTHY; node group RUNNING with matching `cluster_id`.
2. **Load live rules** via YC JSON (`protocol_name`, nested ports/CIDR/targets).
3. **Exact match all 12 rules** (SG, description, direction, protocol, ports, CIDR, `security_group_id`, `predefined_target`). **Unknown extra rules → fail.**
4. **Backup** to LOCALAPPDATA (UTF-8 no BOM) + lineage/serial/SHA256.
5. **Idempotent import loop** (skipped on `-DryRun`):
   - correct State `id` (== live `rule_id`) → skip
   - stale id → `state rm` then import
   - missing → `terraform import <addr> <sg_id>:<rule_id>`
   - `terraform state show` failure is **never** treated as “resource absent”
6. **Inventory:** all 12 rule addresses present; total state size **25** (or **26** if `terraform_data.sg_rules_ready` already tracked).
7. **Plan Gate:** `terraform plan -out …` then `terraform show -json`; analyze `resource_changes[].change.actions`. **Only `no-op` allowed** for managed addresses. Any create/update/delete/replace **blocks**; apply is **not** run.
8. Every external command checks **`$LASTEXITCODE`**.

### Rule catalog (12)

| TF address | Description key |
|------------|-----------------|
| `...master_self` | Internal cluster communication within this SG |
| `...master_lb_healthchecks` | Load balancer health checks (platform predefined) |
| `...master_api_443[0]` | Kubernetes API HTTPS from approved admin CIDRs only |
| `...master_api_6443[0]` | Kubernetes API 6443 from approved admin CIDRs only |
| `...master_from_nodes` | Nodes to master |
| `...master_egress` | Master egress (control-plane, NTP, metric-server, managed services) |
| `...nodes_self` | Node-to-node within SG |
| `...nodes_from_master` | Master to nodes |
| `...nodes_lb_healthchecks` | Load balancer health checks (platform predefined) |
| `...nodes_icmp_private` | ICMP health checks from Yandex Cloud private ranges |
| `...nodes_pod_service_cidrs` | Pod and Service CIDR traffic (cluster networking) |
| `...nodes_egress` | Node egress (registry pulls, OS updates) |

`nodes_nodeport` must remain **absent**.

## Explicitly excluded

| Action | Why excluded |
|--------|----------------|
| Hand-edit `terraform.tfstate` JSON | Corrupts serial/lineage |
| `terraform state push` | Easy to clobber remote; not needed |
| `-SkipPlan` / bypassing Plan Gate | Forbidden |
| Blind `terraform apply` | Can wipe rules / replace cluster |
| Selecting “first” MK8s cluster via CLI | Must use state-derived IDs |

## SG descriptions

Desired (no cloud mutation by script):

- Master: `Managed Kubernetes master SG (credit-scoring)`
- Nodes: `Managed Kubernetes nodes SG (credit-scoring)`

## Kubernetes dependency / destroy order

`module.kubernetes` takes `security_group_dependency_ids = module.network.security_group_rule_ids`.

**Create:** VPC → SG shells → SG rules → (IAM) → cluster → node group
**Destroy:** node group/cluster first → SG rules → SG shells → subnet/VPC

## Acceptance criteria

- `Test-SgPlanGate.ps1` exit 0 (no-op / create / update / delete / replace / malformed)
- DryRun exit 0
- Real run exit 0; backup under LOCALAPPDATA with valid lineage/serial/SHA256
- 12 rule addresses in state; State `id` == live `rule_id`
- Plan Gate: no create/update/delete/replace on managed resources
- Script never runs `apply` / `destroy` / `state push`

## Rollback

1. Do **not** delete live “Nodes to master”.
2. Restore prior state object version from Object Storage **or** LOCALAPPDATA `terraform state pull` backup.
3. Re-run script (idempotent) after fixing mapping.
