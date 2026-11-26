# CLOUD_RUNTIME_VERIFICATION — Block 11.9.1

Evidence classes: **STATIC** | **LOCAL** | **CLOUD_INFRA** | **CLOUD_APP** | **OPS**

Do not mark PASS for levels not executed.

## Infrastructure

| Check | Level | Result | Notes |
|-------|-------|--------|-------|
| Terraform validate / mock tests | STATIC | PASS | Re-run this block |
| Remote State in Object Storage | CLOUD_INFRA | PASS | Operator: 14 resources |
| terraform apply (initial + recovery) | CLOUD_INFRA | PASS | 2 add / 4 change / 0 destroy (recovery); dual-SG defect during recovery |
| MK8s version | CLOUD_INFRA | PASS | 1.34.x REGULAR; HEALTHY/RUNNING |
| Master min preset | CLOUD_INFRA | PASS | `s-c2-m8` |
| Node group | CLOUD_INFRA | PASS | RUNNING; fixed size 1; standard-v3 4c/16g/64ssd NAT |
| Worker Ready | OPS | PASS | After manual SG restore |
| Calico provider | CLOUD_INFRA | PASS | `network_policy.provider=CALICO` |
| Calico pods Running | OPS | PASS* | Observed Running; *intermittent kubectl TLS timeouts |
| Metrics Server pods | OPS | PASS* | 2/2 Running when listed |
| Metrics API node usage | OPS | PASS | Returned CPU ~74m-class, memory ~1.3Gi-class |
| kubectl TLS stability | OPS | FAIL / intermittent | Periodic `TLS handshake timeout`; verification not disabled |
| NetworkPolicy enforcement (+/−) | CLOUD_APP | NOT_EXECUTED | Needs app + explicit tests |
| HPA scale | CLOUD_APP | NOT_EXECUTED | |
| Real ONNX inference in cloud | CLOUD_APP | NOT_EXECUTED | |
| terraform destroy / YC empty checks | OPS | PASS | Operator destroy + CLI absence checks (Block 11.13/11.14) |
| Final billing statement | OPS | NOT_VERIFIED | UI grant burn preliminary only — see FINAL_COST_REPORT.md |
| Cloud ML app deploy | CLOUD_APP | ABORT | ABORT_CLOUD_APP — see FINAL_CLOUD_EXPERIMENT_REPORT.md |

## CIDR alignment

| Source | Pod (cluster) CIDR | Service CIDR |
|--------|--------------------|--------------|
| Live `ip_allocation_policy` | `10.112.0.0/16` | `10.96.0.0/16` |
| TF network module (after fix) | `10.112.0.0/16` | `10.96.0.0/16` |
| TF before fix (misnamed defaults) | labeled 10.96 / 10.112 swapped | both CIDRs still present in allowlist |

## Security posture (config + live intent)

| Control | Status |
|---------|--------|
| SSH to nodes from Internet | Closed (no rule) |
| NodePort public | Disabled (`enable_nodeport_ingress=false`) |
| API admin CIDR | Restricted (not `/0`) |
| Dual SG rule management | **Fixed in code**; 12 rules migrated in experiment |

## Known incident

Recovery Apply deleted “Nodes to master” → worker `NOT_CONNECTED` → manual rule restore → Ready. See `RUNTIME_REMEDIATION_REPORT.md`.
