# Resource Capacity Report — Block 11.5

**Node:** 1× standard-v3 · 4 vCPU (100%) · 16 GB RAM · 64 GB network-ssd · Calico
**Master:** Managed zonal basic (~2 vCPU / 8 GB) — not schedulable for pods.

## Allocatable estimate

| | Capacity | Approx. allocatable* |
|-|----------|----------------------|
| CPU | 4000m | ~3500–3800m |
| Memory | 16 Gi | ~14–15 Gi |
| Ephemeral / disk | 64 GB | OS + images + logs; keep images lean |

\*Exact kube-reserved values appear after node Ready (`kubectl describe node`). Confirm before loading full observability.

## Application requests (staging overlay)

| Workload | CPU req | Mem req | CPU lim | Mem lim | Notes |
|----------|---------|---------|---------|---------|-------|
| API (×1 default) | 100m | 256Mi | 1 | 512Mi | staging `patch-resources` |
| models initContainer | 50m | 32Mi | 200m | 64Mi | copies ONNX FP32 + preprocessor |
| frontend | 25m | 32Mi | 200m | 64Mi | base |
| **App baseline (1 API)** | **~175m** | **~320Mi** | — | — | |

Production HPA (`minReplicas: 2`, `maxReplicas: 6`) is **not** in staging overlay. For cloud experiment: apply a **capped** HPA (`min=1`, `max=3`) so scale-up stays on **pods**, never VMs.

## System / cluster add-ons

| Component | CPU/Mem (order) | Required? |
|-----------|-----------------|-----------|
| kubelet / kube-proxy / Calico | ~300–600m / ~0.5–1 Gi | Yes |
| Metrics Server | ~100m / ~128Mi | Yes for HPA |
| ingress-nginx (if used) | ~100–200m / ~128–256Mi | Only if LB path |
| CoreDNS | small | Yes (MK8s) |

## Observability (from compose sizing → K8s planning)

| Component | Compose cpus | Compose mem | Experiment |
|-----------|--------------|-------------|------------|
| Prometheus | 0.50 | 384m | Recommended |
| Grafana | 0.50 | 384m | Recommended |
| Alertmanager | 0.25 | 128m | Optional |
| Alloy | 0.25 | 192m | Optional |
| Loki | 0.50 | 256m | Optional / defer |
| alert-webhook | 0.10 | 64m | Optional |

**Full stack ≈ 2.6 CPU + ~1.9 Gi** compose caps — fits **with** API/frontend **only if** system headroom checked and Loki/Alloy deferred if allocatable is tight.

## Feasibility matrix

| Goal | Fit on 1 worker? | Notes |
|------|------------------|-------|
| FastAPI + real ONNX FP32 + preprocessor | YES | Models image / initContainer; do not use CI synthetic model |
| Frontend | YES | |
| Prometheus + Grafana | YES | Deploy after API Ready |
| Metrics Server + HPA (pod-only) | YES | Install/verify metrics-server; cap maxReplicas |
| Calico NetworkPolicy +/− tests | YES | Calico enabled at cluster level |
| Loki + Alloy + Alertmanager | MARGINAL | Sequential; drop Loki first if pressure |
| HPA via extra VMs | NO | Forbidden by quota + config locks |

## Sequential bring-up (recommended)

1. Cluster + node Ready; confirm allocatable.
2. Metrics Server (if not preinstalled).
3. Namespace + NetworkPolicies + secrets (GHCR pull) + ConfigMaps.
4. Models+API (1 replica) → readiness `/health/ready` → real inference.
5. Frontend → E2E (port-forward or Ingress).
6. Prometheus → scrape API → Grafana dashboard.
7. HPA (max 3) → CPU load → scale-up/down **pods only**.
8. Optional: Alertmanager → Alloy → Loki **last**.

## Pressure risks

- API limit 1 CPU × HPA 3 ≈ 3 CPU limits + obs → CPU throttling expected under load (acceptable for experiment).
- Memory: 3×512Mi API + obs + system ≈ safe under 14 Gi if Loki PV not oversized.
- Image pulls from GHCR need `imagePullSecret`; node NAT already enabled.
- Rolling update of API: use `maxUnavailable=0` / small surge — pod-level only; **node** rolling uses `max_expansion=0` (brief downtime possible).
