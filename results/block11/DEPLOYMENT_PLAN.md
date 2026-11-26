# Deployment & Verification Plan — Block 11.5

**Status gate:** wait for explicit user approval before any `terraform plan` against live backend / `apply` / resource creation.

## Preconditions (operator)

1. Copy `terraform.tfvars.example` → `terraform.tfvars` (gitignored): real `cloud_id`, `folder_id`, admin CIDR `/32`.
2. Export `YC_TOKEN` (or SA key file) — never commit / never echo.
3. Optional remote state bootstrap (see backend examples) — bucket **not** created in prep stage.
4. Confirm console quotas: Compute 4/16/64; public IPs ≥2; MK8s clusters ≥1; no conflicting VMs (folder currently empty per read-only `yc` list).
5. GHCR: private packages readable via pull token → K8s `imagePullSecret`; pin images by **digest** when available.
6. Model path: production ONNX FP32 + preprocessor (local SHA256 verified); **do not** publish model artifacts to a public registry; **do not** swap CI synthetic model.

## Scenario checklist

| # | Scenario | How | Pass criteria | Evidence (sanitized) |
|---|----------|-----|---------------|----------------------|
| 1 | Create infra | `terraform plan` then approved `apply` in `cloud-experiment` | Cluster RUNNING; 1 CPU NG; GPU NG absent | plan/apply logs redacted; `yc managed-kubernetes cluster get` status |
| 2 | kubectl | `yc managed-kubernetes cluster get-credentials --external` | `kubectl get ns` works from admin CIDR | context name only |
| 3 | Node Ready | `kubectl get nodes -o wide` | 1 node Ready; Calico pods Ready | node name/zone; no public SSH ports |
| 4 | Deploy app | `kubectl apply -k k8s/overlays/staging` + digests + pull secret | Deployments Available | image digests, not tokens |
| 5 | Probes | hit `/health/live`, `/health/ready` | live 200; ready 200 after model load | HTTP codes + latency |
| 6 | Real inference | POST predict with real schema | 200 + score; ONNX FP32 path | anonymized request/response |
| 7 | Frontend E2E | port-forward **or** Ingress if LB enabled | UI loads; predict via UI | screenshot sans PII |
| 8 | Prometheus | deploy Prom; scrape API metrics | targets UP; key series present | metric names only |
| 9 | HPA up/down | HPA min=1 max=3; CPU load | replicas increase then decrease; **node count stays 1** | `kubectl get hpa,nodes` |
| 10 | Calico NP +/− | allow path vs deny cross-pod | positive 200; negative timeout/deny | curl from ephemeral pods |
| 11 | Rolling update | change annotation/image patch | surge pods; zero/minimal downtime | rollout status |
| 12 | Rollback | `kubectl rollout undo` | previous revision Ready | revision history |
| 13 | Evidence pack | copy logs/metrics/screens into `results/block11/evidence/` | no secrets, no PII, no cloud IDs if policy | file list |
| 14 | Destroy | `terraform destroy` after app cleanup | TF exit 0 | destroy summary |
| 15 | No paid leftovers | console: VMs, disks, IPs, LB, MK8s, YCR, buckets (except optional tfstate) | empty compute/k8s | checklist ticks |
| 16 | Billing | Billing → consumption for window | ≤500 ₽; grant covers | amount + timestamp (no account numbers) |

## GHCR / images

- CI publishes to `ghcr.io/<owner>/credit-scoring-*` with `packages: write` (existing workflows).
- Cloud pull: create docker-registry secret; set `imagePullSecrets` on SA/pods.
- Prefer `sha-<gitsha>` tags or digests from publish job output.
- Models image must contain **production** ONNX FP32 + preprocessor matching protected SHA256 — build from local artifacts privately; do not push raw model files to a public package.

## HPA rule

**Never** scale Managed Kubernetes node group or create extra VMs for HPA. Only Deployment replicas.

## Abort criteria (stop & destroy)

- Billing notification 300 ₽ before goals done and no clear finish <1h
- Quota errors creating second node
- Accidental GPU / autoscaling / `0.0.0.0/0` API exposure
- Any own-funds charge risk
