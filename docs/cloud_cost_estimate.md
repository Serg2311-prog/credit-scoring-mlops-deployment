# Cloud Cost Estimate — Yandex Cloud (Stage 3B)

**Дата оценки:** 2026-11-22
**Фактические расходы этапа 3Б:** **0 ₽** (ресурсы не создавались, `apply` не выполнялся).

> **Block 11 billing (do not rewrite Stage 3B planning numbers above):** confirmed operator billing on **2026-11-26** — consumption **56,34 ₽**, grant-covered **56,34 ₽**, due **0,00 ₽**. Future accruals are not guaranteed. See [`../results/block11/FINAL_COST_REPORT.md`](../results/block11/FINAL_COST_REPORT.md).

## Источники тарифов

| Источник | URL | Дата обращения |
| --- | --- | --- |
| Managed Kubernetes pricing | https://yandex.cloud/ru/docs/managed-kubernetes/pricing | 2026-11-22 |
| Compute Cloud pricing | https://yandex.cloud/ru/docs/compute/pricing | 2026-11-22 |
| Object Storage / Registry / Logging | соответствующие docs + калькулятор YC | 2026-11-22 |
| Вторичная сводка master rates | публичное сравнение (сент. 2026), не оферта | использовать только как ориентир |

Официальная страница MK8s подтверждает модель: **мастер тарифицируется отдельно**, worker — по **Compute Cloud**, egress — отдельно (первые **100 ГБ/мес** бесплатно).
Точные числа для мастера в HTML-документации могут отличаться по региону/дате — **перед apply пересчитать в [калькуляторе](https://yandex.cloud/ru/prices) / прайс-листе**.

## Проверенные ставки Compute (регион Россия, из docs, с НДС)

Из примера официальной документации Compute (Intel Ice Lake / 100% vCPU):

| Ресурс | Ставка | Источник |
| --- | --- | --- |
| 1 × 100% vCPU · час | **1,24 ₽** | compute/pricing пример |
| 1 ГБ RAM · час | **0,33 ₽** | compute/pricing пример |

Ориентир для master MK8s (вторичный источник, сент. 2026, **перепроверить**):

| Ресурс | Ориентир |
| --- | --- |
| master vCPU · час | ~1,76 ₽ |
| master RAM ГБ · час | ~0,46 ₽ |

## Формулы (без выдуманных итогов)

Пусть \(H = 730\) часов/месяц (округление).

```text
nodes_month ≈ H * N * (cores * rate_vcpu + memory_gb * rate_ram)
             + disk_gb * rate_disk_month
             + public_ip_month (если есть)

master_month ≈ H * (master_vcpu * rate_master_vcpu + master_ram_gb * rate_master_ram)
               # точные rate_* — из прайс-листа MK8s на дату apply

storage_month ≈ stored_gb * rate_storage + ops * rate_ops
registry_month ≈ stored_gb * rate_registry
logging_month  ≈ ingested_gb * rate_logging (+ retention effects)
egress_month   ≈ max(0, egress_gb - 100) * rate_egress
```

## Сценарии конфигурации (из Terraform defaults)

### Staging (`cs-stg`)

- Master: zonal, baseline (ориентир 2 vCPU / 8 GB — уточнять в UI)
- Nodes: **1** × `standard-v3`, **2 vCPU / 4 GB**, preemptible=true, disk 64 GB
- Registry + private bucket + logging 7 дней
- Public master IP: **false** по умолчанию

### Production (`cs-prod`)

- Master: zonal (HA **не** включён по умолчанию — дороже)
- Nodes: **2** × `standard-v3`, **2 vCPU / 8 GB**, non-preemptible, disk 100 GB
- Logging 30 дней
- Public master IP: **false**

### Пример расчёта только worker compute (проверенные ставки)

Staging worker (non-preemptible эквивалент для оценки верхней границы):

```text
730 * (2*1.24 + 4*0.33) = 730 * (2.48 + 1.32) = 730 * 3.80 ≈ 2 774 ₽/мес
```

Production workers (2 nodes):

```text
2 * 730 * (2*1.24 + 8*0.33) = 2 * 730 * (2.48 + 2.64) = 2 * 730 * 5.12 ≈ 7 475 ₽/мес
```

Добавить: master MK8s, диски, NAT/IP, registry, storage, logging, egress.
Preemptible staging снижает compute, но не обнуляет master/диски.

**Итог этапа 3Б:** 0 ₽ факта.
**Прогноз после apply:** считать калькулятором; ориентир порядка **нескольких–десятка+ тыс. ₽/мес** на staging+prod вместе при круглосуточной работе.

## Минимизация затрат

1. Не делать `apply` без необходимости.
2. Staging: preemptible nodes, 1 node, короткий log retention, останавливать кластер вне работы (master перестаёт тарифицироваться; диски/IP могут остаться).
3. Не включать HA master / GPU / лишние LB.
4. Держать артефакты маленькими (ONNX ~60 KB + joblib ~6 KB).
5. Отдельные budget alerts в консоли YC.

## Безопасное удаление (будущее)

```powershell
# Только после явного разрешения
terraform -chdir=infra/terraform/environments/staging destroy
terraform -chdir=infra/terraform/environments/production destroy
```

Порядок: workloads → node group/cluster → registry images → bucket objects → KMS → network.
Проверить отсутствие orphan disks/IP/LB в консоли.
