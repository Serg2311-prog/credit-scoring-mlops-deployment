# Stage 5 Validation Report — Monitoring & Observability

**Date:** 2026-11-22  
**Scope:** Local Docker Compose observability (Prometheus, Grafana, Loki, Alloy, Alertmanager)  
**Cloud / Terraform apply / paid SaaS:** **not used**  
**Commit/push:** not performed as part of this stage work session

## Implementation summary

| Deliverable | Path / notes |
| --- | --- |
| Compose overlay | `docker-compose.observability.yml` (+ network `credit-scoring-net` in `docker-compose.yml`) |
| Prometheus | `monitoring/prometheus/` (`prom/prometheus:v3.2.1`) |
| Alertmanager | `monitoring/alertmanager/` + local webhook sink |
| Loki | `monitoring/loki/loki.yml` (72h retention, `grafana/loki:3.4.2`) |
| Alloy | `monitoring/alloy/config.alloy` (`grafana/alloy:v1.7.5`) |
| Grafana provisioning | `monitoring/grafana/provisioning/` (`grafana/grafana:11.5.2`) |
| Dashboards | API Overview, Model Inference, Infrastructure, Application Logs |
| Runbook | `docs/stage5_runbook.md` |
| Architecture | `docs/architecture/observability.md` |
| Checks | `scripts/observability/check.ps1`, `verify_stack.py`, `fire_test_alert.ps1` |
| App deltas | `INFERENCE_LATENCY` metric; JSON log fields `level` + `service` |

## Local verification results (2026-11-22)

| Check | Result |
| --- | --- |
| `docker compose -f docker-compose.yml -f docker-compose.observability.yml config` | **PASS** |
| `promtool check config` / `check rules` (5 rules) | **PASS** |
| Stack `up -d --build` | **PASS** — api, prometheus, grafana, loki, alloy, alertmanager, alert-webhook, cadvisor started |
| Prometheus scrapes API | **PASS** — target `credit-scoring-api` health=up |
| Grafana datasources | **PASS** — prometheus + loki |
| Grafana dashboards provisioned | **PASS** — 4 dashboards listed via API |
| Loki receives logs | **PASS** — labels include `service`, `level`, `request_id`, … |
| Alertmanager test alert | **PASS** — `Stage5TestAlert` via `fire_test_alert.ps1` |
| `scripts/observability/verify_stack.py` | **PASS** (RESULT: PASS) |
| Unit tests (`test_metrics`, `test_logging_json`) | **PASS** |

## Known limitations

1. **8 GB RAM:** stack is capped (API 1.5 GiB + obs ~1.5 GiB). Close other compose projects.  
2. **cAdvisor on Docker Desktop (Windows):** worked in this run (healthy); may vary by host mounts.  
3. **Grafana default password `admin/admin`:** local lab only.  
4. **No cloud alerting channels** by design (no SMTP/Telegram secrets in Git).  
5. Observability does **not** deploy to Yandex Cloud or production clusters.

## Not claimed

- Production / staging cloud monitoring  
- Yandex Monitoring integration  
- Long-term remote retention  
- Stage 6+ work
