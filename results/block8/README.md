# Block 8 / 8.1 — Monitoring / Alerting / Drift evidence

Local Docker Desktop verification (Windows, CPU-only, ~8 GB RAM). No cloud resources.

## Reproduce — observability + log alert (Block 8.1)

```powershell
docker compose -f docker-compose.yml -f docker-compose.observability.yml `
  -f docker-compose.observability.e2e.yml up -d --build --scale frontend=0

./.venv\Scripts\python.exe scripts\observability\verify_stack.py --retries 8 --sleep 5
./.venv\Scripts\python.exe scripts\block8\e2e_observability.py inject-error-log --probe htt<REDACTED_PATH>
./.venv\Scripts\python.exe scripts\block8\e2e_observability.py wait-alert --alertname APIErrorLogsDetected --timeout 180 --output results\block8\log_alert_firing.json
# wait for resolve; capture webhook logs
docker logs credit-scoring-alert-webhook --tail 50 > results\block8\webhook_after_log_alert.log

# Drift gauges (job filter required)
Invoke-RestMethod 'htt<REDACTED_PATH>"drift-metrics-exporter"}'

docker compose -f docker-compose.yml -f docker-compose.observability.yml `
  -f docker-compose.observability.e2e.yml down
```

E2E overlay vs production:

- `alerts.e2e.yml` — shorter `for:` (metric alerts only; production thresholds unchanged in `alerts.yml`)
- separate `e2e-log-probe` container (not in production API image/routes)
- `drift-metrics-exporter` on `:9108`
- Alloy `config.e2e.alloy` scrapes API + probe

## Reproduce — online A/B (isolated; sequential after observability down)

```powershell
docker compose -f docker-compose.yml -f docker-compose.ab.e2e.yml up -d --no-build --scale frontend=0
./.venv\Scripts\python.exe scripts\block8\e2e_online_ab.py --n-ids 1000 --n-http 150 --output results\block8\online_ab_evidence.json
docker compose -f docker-compose.yml -f docker-compose.ab.e2e.yml down
```

## Reproduce — drift demo / concept / Airflow decision (no Docker)

```powershell
./.venv\Scripts\python.exe -m src.monitoring.cli demo
./.venv\Scripts\python.exe -c "from src.monitoring.concept_drift_experiment import generate_concept_drift_scenarios; import json; r=generate_concept_drift_scenarios(); open('results/block8/concept_drift_experiment.json','w',encoding='utf-8').write(json.dumps(r,indent=2))"
./.venv\Scripts\python.exe scripts\block8\e2e_airflow_triggers.py
```

## Key evidence (Block 8.1)

| File | Meaning |
| --- | --- |
| `registry_immutability_demo.json` | Production registry SHA before/after dual demo |
| `api_probe_absent_runtime.json` | Production API probe 404 |
| `log_alert_firing.json` / `log_alert_resolved.json` | Loki ruler chain |
| `webhook_after_log_alert.log` / `webhook_after_resolve.log` | Alertmanager webhook |
| `prometheus_ml_metrics_by_job.json` | Offline `ml_*` from exporter |
| `cadvisor_labels_evidence.json` | Real cAdvisor label keys |
| `online_ab_evidence.json` | Assignment + HTTP A/B |
| `online_ab_challenger_unavailable.json` | Missing challenger fallback |
| `concept_drift_experiment.json` | Controlled A–D scenarios |
| `airflow_trigger_decisions.json` | Decision layer only |
| `sha_before_block81.txt` / `sha_after_block81.json` | Six production artifact hashes |
| `BLOCK81_FINAL_REPORT.md` | 15-point acceptance report |

## Status legend used in reports

- **VERIFIED** — real local evidence in this folder / tests
- **IMPLEMENTED_NOT_VERIFIED** — code present, live check not done
- **BLOCKED** — environment limitation (e.g. Docker Desktop labels, no cloud cluster)
- **NOT_EXECUTED** — intentionally skipped (cloud apply, full retrain, Block 9)
