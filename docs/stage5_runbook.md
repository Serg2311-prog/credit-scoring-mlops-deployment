# Stage 5 Runbook — Local Observability

Local Docker Compose stack only. No cloud credentials.

## URLs

| Service | URL | Notes |
| --- | --- | --- |
| API | http://127.0.0.1:8000 | `/health/live`, `/health/ready`, `/metrics` |
| Prometheus | http://127.0.0.1:9090 | Targets, Graph, Alerts |
| Alertmanager | http://127.0.0.1:9093 | Active alerts |
| Grafana | http://127.0.0.1:3000 | admin / admin (local only) |
| Loki | http://127.0.0.1:3100 | ready `/ready` |
| Alloy | http://127.0.0.1:12345 | collector UI/ready |
| cAdvisor | http://127.0.0.1:8088 | container metrics |
| Alert webhook | http://127.0.0.1:9095/health | local sink |

## Start / stop (PowerShell)

```powershell
cd <repo>
# Requires models/credit_scoring_nn.onnx + models/preprocessor.joblib
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build

# Generate traffic (metrics + logs)
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready

docker compose -f docker-compose.yml -f docker-compose.observability.yml ps
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
# Keep volumes: omit -v. Wipe data: add -v
```

## Diagnostics

```powershell
docker compose -f docker-compose.yml -f docker-compose.observability.yml ps
docker logs credit-scoring-api --tail 100
docker logs credit-scoring-prometheus --tail 100
docker logs credit-scoring-loki --tail 100
docker logs credit-scoring-alloy --tail 100
docker logs credit-scoring-alertmanager --tail 50
docker logs credit-scoring-alert-webhook --tail 50
```

## Check metrics

```powershell
# Raw exporters
(Invoke-WebRequest http://127.0.0.1:8000/metrics).Content | Select-String credit_scoring_

# Prometheus target
Invoke-RestMethod http://127.0.0.1:9090/api/v1/targets |
  Select-Object -ExpandProperty data |
  Select-Object -ExpandProperty activeTargets |
  Where-Object { $_.labels.job -eq 'credit-scoring-api' }

# PromQL examples (Prometheus UI → Graph)
# sum(rate(credit_scoring_http_requests_total[1m]))
# histogram_quantile(0.95, sum by (le) (rate(credit_scoring_http_request_latency_seconds_bucket[5m])))
# credit_scoring_model_ready
```

## Check logs (Grafana / Loki)

1. Open Grafana → Explore → datasource **Loki**.
2. Query: `{service="credit-scoring-api"}`
3. Errors: `{service="credit-scoring-api"} |= "ERROR"`
4. By request: `{service="credit-scoring-api"} |= "<request_id>"`

JSON fields: `timestamp`, `level`, `service`, `request_id`, `endpoint`, `status_code` (no request bodies / PII).

## Metric alert E2E (real Prometheus rule — preferred)

Uses production rules (`for: 1m` on `APIDown`) or Block 8 E2E overlay (`alerts.e2e.yml`, `for: 15s`):

```powershell
# Optional faster pending window:
# docker compose -f docker-compose.yml -f docker-compose.observability.yml `
#   -f docker-compose.observability.e2e.yml up -d --no-build

docker stop credit-scoring-api
.\.venv\Scripts\python.exe scripts\block8\e2e_observability.py wait-alert --alertname APIDown --timeout 180 --output results\block8\metric_alert_firing.json
docker logs credit-scoring-alert-webhook --tail 20
docker start credit-scoring-api
# Wait until Alertmanager no longer lists active APIDown; webhook status=resolved
```

| Alert | Meaning | Diagnose | Recover | Resolved when |
| --- | --- | --- | --- | --- |
| APIDown | scrape `up==0` | `Invoke-RestMethod http://127.0.0.1:9090/api/v1/targets` | start/recreate `api` | `up==1` long enough |
| HighHTTP5xxRate | 5xx share >5% | `/metrics`, API logs | fix app/model; reduce bad traffic | rate below threshold |
| HighP95Latency | p95 >1s | PromQL histogram_quantile | scale/CPU; check batch size | p95 below 1s |
| ModelNotReady | gauge==0 | `/health/ready`, mounts | fix ONNX/preprocessor | ready=1 |
| APIMetricsAbsent | job missing | prometheus.yml / network | restore scrape job | job present |

## Log-based alert E2E (Loki Ruler — required)

Rule: `monitoring/loki/rules/fake/rules.yml` → `APIErrorLogsDetected`
Pipeline: API structured ERROR → Alloy → Loki → ruler → Alertmanager → webhook.

```powershell
# Block 8.1: production API has NO /internal/e2e/log-error.
# Start observability + E2E overlay (includes test-only e2e-log-probe on :9109):
# docker compose -f docker-compose.yml -f docker-compose.observability.yml `
#   -f docker-compose.observability.e2e.yml up -d --build --scale frontend=0

.\.venv\Scripts\python.exe scripts\block8\e2e_observability.py inject-error-log --probe http://127.0.0.1:9109
.\.venv\Scripts\python.exe scripts\block8\e2e_observability.py wait-alert --alertname APIErrorLogsDetected --timeout 180 --output results\block8\log_alert_firing.json
docker logs credit-scoring-alert-webhook --tail 20
# After ~2m without new ERROR lines → alert resolves; webhook status=resolved
```

Do **not** treat Prometheus `HighHTTP5xxRate` as a substitute for this log rule.

## Synthetic Alertmanager test (not a rule evaluation)

```powershell
.\scripts\observability\fire_test_alert.ps1
# UI: http://127.0.0.1:9093
docker logs credit-scoring-alert-webhook --tail 20
```

Rule validation (no stack required):

```powershell
docker run --rm --entrypoint promtool -v "${PWD}/monitoring/prometheus:/etc/prometheus:ro" `
  prom/prometheus:v3.2.1 check rules /etc/prometheus/alerts.yml
```

## Automated verification

```powershell
.\scripts\observability\check.ps1
```

## Typical failures

| Symptom | Likely cause | Recovery |
| --- | --- | --- |
| API unhealthy / ready 503 | Missing ONNX/joblib mounts | Place artifacts under `models/`, recreate api |
| Prometheus target DOWN | API not on same compose network / still starting | Wait; `docker compose ... ps`; check `api:8000` |
| Loki no labels | Alloy cannot read docker.sock / no API logs yet | Hit API endpoints; check alloy logs; Docker Desktop file sharing |
| Grafana empty dashboards | Datasource provisioning failed | Check grafana logs; open Connections → Data sources |
| cAdvisor unhealthy on Windows | Docker Desktop mount/privilege limits | Infra dashboard may be partial; API/Prom/Loki still usable |
| OOM / laptop freeze | Too many stacks at once | `down` unused compose projects; keep this stack only |

## Recovery after failure

```powershell
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
.\scripts\observability\check.ps1
```

Persistent data lives in named volumes (`prometheus-data`, `loki-data`, `grafana-data`, …). Remove with `down -v` only if you intend to wipe local TSDB/logs.
