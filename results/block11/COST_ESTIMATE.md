# Cost Estimate — Block 11.5 (RUB, VAT included)

**Budget cap:** ≤ 500 RUB from grant · **Own spend:** 0 RUB · **Target window:** 4 hours
**Currency:** RUB (Russian billing account). No USD conversion used as proof.

## Tariff sources

| Item | Rate | Source class |
|------|------|--------------|
| Ice Lake 100% vCPU | 1.24 ₽ / vCPU·h | OFFICIAL — Compute pricing (docs, effective 30 Apr 2026) |
| Ice Lake RAM | 0.33 ₽ / GB·h | OFFICIAL — same |
| network-ssd (быстрый диск) | 0.0199 ₽ / GB·h | OFFICIAL — same |
| Public IP (active) | 0.26352 ₽ / h | OFFICIAL — VPC pricing |
| MK8s master vCPU | 1.76 ₽ / vCPU·h | **SECONDARY** — third-party digest of YC Russia prices (Sep 2026); official pricing page table is image-only in fetch |
| MK8s master RAM | 0.46 ₽ / GB·h | **SECONDARY** — same |
| Egress | first 100 GB/mo free, then 1.42 ₽/GB | OFFICIAL (Compute/MK8s docs) |
| Cloud Logging / YCR / KMS | — | Optional; rates **NOT_VERIFIED** in this report (disabled in minimal config) |

> Treat master line as **estimate with secondary verification**. Re-check calculator/console before apply.

## Minimal experiment basket (recommended)

**Included (required for goals):**
- MK8s zonal basic master ~ 2 vCPU / 8 GB
- 1× worker standard-v3: 4 vCPU 100%, 16 GB RAM, network-ssd 64 GB, non-preemptible, NAT public IP
- Master public IP (CIDR-restricted API)
- VPC / SG / IAM (free)

**Excluded (optional / deferred):**
- Yandex Container Registry → use existing GHCR
- Artifacts Object Storage + KMS
- Cloud Logging / master logging
- Application Load Balancer / NLB (use `kubectl port-forward` for E2E unless LB explicitly enabled)
- Extra PVCs beyond node boot disk
- GPU node group
- Second worker / autoscaling

## Hourly arithmetic

| Component | Formula | ₽/h |
|-----------|---------|-----|
| Master | `2×1.76 + 8×0.46` | 7.20 |
| Worker compute | `4×1.24 + 16×0.33` | 10.24 |
| Worker disk | `64×0.0199` | 1.2736 |
| Worker public IP | 1×0.26352 | 0.26352 |
| Master public IP | 1×0.26352 | 0.26352 |
| **Total (minimal)** | | **≈ 19.24** |

Object Storage for Terraform state only (bootstrap later): expect **≪ 1 ₽** for 4h at tiny object size — treat as noise; exact Object Storage RUB/GB **NOT_VERIFIED** here.

## Totals by duration

| Hours | Minimal estimate (₽) | vs 500 ₽ budget |
|-------|----------------------|-----------------|
| 1 | ≈ 19.2 | OK |
| **4 (target)** | **≈ 77** | **OK (~15% of cap)** |
| 8 | ≈ 154 | OK |
| 24 | ≈ 462 | OK but thin margin if extras/LB added |

**Contingency:** keep ≥ 100 ₽ headroom → do not leave cluster > ~20h; destroy promptly; avoid LB/YCR/KMS unless needed.

## If optional services enabled

| Add-on | Effect |
|--------|--------|
| Cloud Logging (short retention) | Small; rate **NOT_VERIFIED** — prefer off |
| YCR | Storage + operations; prefer GHCR |
| KMS | Key-hour charge; prefer off |
| NLB/ALB | Material hourly add — enable only for Ingress E2E |
| Persistent Volumes | Disk-hour same as network-ssd rate |
| Full Loki stack | No cloud PaaS fee if in-cluster; burns node capacity, not extra YC SKU |

## Minimal configuration verdict

`cloud-experiment` defaults (`enable_registry/storage/monitoring=false`, single non-GPU worker, no autoscaling) **meet experiment goals** within **~77 ₽ / 4h**, well under 500 ₽ grant slice.
