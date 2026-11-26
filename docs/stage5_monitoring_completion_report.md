# Stage 5 / Block 8 + 8.1 — Monitoring completion report

**Date:** 2026-11-25
**HEAD baseline:** `871f467` (pre-Block-8 working tree; Block 8/8.1 uncommitted)
**Environment:** Windows PowerShell, Docker Desktop, CPU-only, ~8 GB RAM
**Commit/push / terraform apply:** not performed

## Соответствие требованиям этапа 5

| Requirement | Status |
| --- | --- |
| Prometheus app + infra metrics | **VERIFIED** (API scrape; cAdvisor job up; Docker Desktop: only `id`/`instance`/`job`/`service` labels — no container `name`) |
| Grafana dashboards | **VERIFIED** (provisioned; Prometheus+Loki datasources; Model Quality & Drift panels filter `job="drift-metrics-exporter"`) |
| Centralized logging Loki/ELK | **VERIFIED** (Alloy → Loki; LogQL returns structured fields) |
| Log analysis dashboard | **VERIFIED** (Application Logs dashboard; optional in TZ) |
| Alerts on metrics | **VERIFIED** (APIDown pending→firing→webhook→resolved) |
| Alerts on logs | **VERIFIED** (Block 8.1: test-only `e2e-log-probe` → Alloy → Loki ruler `APIErrorLogsDetected` → Alertmanager → webhook firing→resolved) |
| Runbook | **VERIFIED** (`docs/stage5_runbook.md`) |

## Block 8.1 security hardening (E2E log probe)

| Item | Status |
| --- | --- |
| `POST /internal/e2e/log-error` in production API | **REMOVED** — OpenAPI + runtime 404 (`results/block8/api_probe_absent_runtime.json`) |
| `ENABLE_E2E_LOG_PROBE` in API settings | **REMOVED** |
| Test-only injector | **VERIFIED** — `monitoring/e2e-log-probe/` + compose overlay service on `:9109` |
| Production compose (`docker-compose.yml` / `observability.yml`) | **VERIFIED** — no `e2e-log-probe` service (unit test) |

## E2E highlights (Block 8.1 re-run)

- Controlled ERROR via `e2e-log-probe` → Loki stream `service=e2e-log-probe`
- Log alert fire ~08:19:43Z → webhook `status=firing` → resolve ~08:21:13Z → webhook `status=resolved`
- Drift exporter scrape `up{job="drift-metrics-exporter"}=1`; gauges via job filter (do not use unlabeled API defaults)
- cAdvisor: `container_*` series present; identification by cgroup `id` only on Docker Desktop

## Gaps / limits

1. Docker Desktop cAdvisor: **no** `name` / compose-service labels on series — document, do not invent labels.
2. Live Kubernetes cloud monitoring: **NOT_EXECUTED** (no paid cluster); local YAML parse only.
3. No cloud notification channels (local webhook sink only).
4. ~~API process still registers unset `ml_data_drift_*` gauges as 0~~ — **fixed in Block 10.1**: API no longer emits drift gauges; exporter is on the base observability stack with `ml_monitoring_artifact_status`.

## Historical Stage 5 validation snapshot (2026-11-22)

Initial observability stack validation (Prometheus/Grafana/Loki/Alloy/Alertmanager) preceded Block 8/8.1 runtime evidence under `results/block8/`.
