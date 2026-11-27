# Индекс доказательств (Evidence Index)

Относительные ссылки от корня репозитория. Актуальная версия: ветка [`main`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/tree/main).
Оригинальные GPU/Block 7–8 machine-readable evidence сохраняются без renormalize.

---

## Этап 1 — Модель / ONNX / benchmark

| Критерий | Тест | Отчёт | JSON/CSV/plots | Команда | CI |
| --- | --- | --- | --- | --- | --- |
| MLP train / schema | `tests/test_nn.py`, features | [`docs/model_benchmark.md`](model_benchmark.md) | `artifacts/` (local) | `python -m src.nn.train_nn` | `ci-python` |
| ONNX parity | `tests/test_nn.py` | [`docs/stage1_model_optimization_completion_report.md`](stage1_model_optimization_completion_report.md) | [`results/block7/`](../results/block7/) | `scripts/block7_eval.py` | `ci-python` |
| Quantization | unit + deltas | model_benchmark §quant | block7 quant JSON | `python -m src.nn.quantize` | `ci-python` |
| CPU latency | block7 | model_benchmark | block7 CPU JSON | `scripts/block7_eval.py` | — |
| GPU T4 | — | [`docs/gpu_benchmark_colab.md`](gpu_benchmark_colab.md) | [`results/block7/colab/hardened/`](../results/block7/colab/hardened/) | Colab notebook (archived) | — |
| API load | — | stage1 completion | [`results/block7/api_load_summary.json`](../results/block7/api_load_summary.json) | `scripts/api_load_test.py` | — |

---

## Этап 2 — Terraform

| Критерий | Тест | Отчёт | Evidence | Команда | CI |
| --- | --- | --- | --- | --- | --- |
| Modules/envs | `tests/terraform/` | [`docs/terraform_infrastructure.md`](terraform_infrastructure.md) | stage2/3b + block11 | `terraform validate` (`-backend=false`) | `ci-infrastructure` |
| Remote state | — | terraform docs + Block 11 | live then destroyed | operator evidence | — |
| Cloud experiment | — | [`results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md) | apply→destroy | operator YC CLI | — |

---

## Этап 3 — Docker / K8s / DVC

| Критерий | Тест | Отчёт | Evidence | Команда | CI |
| --- | --- | --- | --- | --- | --- |
| Compose API/FE | api integration | [`docs/docker_deployment.md`](docker_deployment.md) | stage3 | `docker compose up -d --build` | `ci-docker` |
| kind Ingress | k8s scripts | [`docs/kubernetes_local_deployment.md`](kubernetes_local_deployment.md) | stage3a/3 | `scripts/k8s_ingress_e2e.ps1` | `ci-kubernetes` |
| DVC | — | stage3 | `dvc.lock` | `python -m dvc repro` | — |
| NetworkPolicy | manifests | stage3 | k8s NP yaml | `scripts/k8s_networkpolicy_verify.ps1` | kubeconform |

---

## Этап 4 — CI/CD

| Критерий | Тест | Отчёт | Evidence | Команда | CI |
| --- | --- | --- | --- | --- | --- |
| Python quality | pytest/black/flake8 | [`docs/cicd_pipeline.md`](cicd_pipeline.md) | Actions runs | `scripts/ci/check.ps1` | `ci-python` |
| Docker+Trivy | workflow | stage4 | Actions | push/PR | `ci-docker` |
| Five primary CI + orchestrator | `ci-*.yml`, `ci-cd.yml` | [`cicd_pipeline.md`](cicd_pipeline.md) | Actions on `5527a55` | push main/PR | `ci-*` |
| CD dry-run | workflows | stage4/5 | local_cd_verify | `scripts/ci/local_cd_verify.ps1` | `cd-staging` |

---

## Этап 5 — Monitoring

| Критерий | Тест | Отчёт | Evidence | Команда | CI |
| --- | --- | --- | --- | --- | --- |
| Prometheus/Grafana | verify_stack | [`docs/stage5_monitoring_completion_report.md`](stage5_monitoring_completion_report.md) | [`results/block8/snapshot_*.json`](../results/block8/) | compose observability | — |
| Metric alert APIDown | e2e_observability | stage5 runbook | `metric_alert_firing.json` / resolved | stop api → wait-alert | — |
| Log alert | e2e-log-probe | stage5/8.1 | `log_alert_*.json`, webhooks | `inject-error-log` | — |
| Runbook | — | [`docs/stage5_runbook.md`](stage5_runbook.md) | — | — | — |
| cAdvisor limits | — | block8 | `cadvisor_labels_evidence.json` | — | — |

---

## Этап 6 — Drift / A/B

| Критерий | Тест | Отчёт | Evidence | Команда | CI |
| --- | --- | --- | --- | --- | --- |
| Data drift | `tests/monitoring/test_data_drift.py` | [`docs/stage6_drift_completion_report.md`](stage6_drift_completion_report.md) | `results/block8/drift/` | `python -m src.monitoring.cli demo` | `ci-python` |
| Concept experiment | `test_concept_drift_experiment.py` | stage6 | `concept_drift_experiment.json` | generate script | `ci-python` |
| Offline A/B | `test_ab_testing.py` | stage6 | demo_summary | monitoring CLI | `ci-python` |
| Online A/B | scripts + unit | stage6 | `online_ab_evidence.json` | `docker-compose.ab.e2e.yml` + `e2e_online_ab.py` | — |
| Registry immutability | `test_registry_immutability.py` | stage6/8.1 | `registry_immutability_demo.json` | dual demo | `ci-python` |
| Drift exporter | `test_prometheus_export.py` | stage6 | `prometheus_ml_metrics_by_job.json` | exporter :9108 | — |

---

## Этап 7 — Airflow

| Критерий | Тест | Отчёт | Evidence | Команда | CI |
| --- | --- | --- | --- | --- | --- |
| DAG structure | `tests/retraining/` | [`docs/stage7_airflow_e2e_report.md`](stage7_airflow_e2e_report.md) | E2E JSON in artifacts/report | compose airflow e2e | `ci-airflow-dag` |
| Triggers | `test_triggers.py` | stage7 runbook | `results/block8/airflow_trigger_decisions.json` | `e2e_airflow_triggers.py` | `ci-python` |
| No auto-promote | pipeline tests | stage7 | E2E reports | — | `ci-python` |

---

## Документация

| Артефакт | Путь |
| --- | --- |
| README | [`README.md`](../README.md) |
| Final report | [`docs/final_project_report.md`](final_project_report.md) |
| Requirements matrix | [`docs/requirements_matrix.md`](requirements_matrix.md) |
| Краткое руководство по запуску и проверке | [`docs/quick_review.md`](quick_review.md) |
| Defense guide | [`docs/defense_guide.md`](defense_guide.md) |
| Architecture | [`docs/architecture/overview.md`](architecture/overview.md) |

---

## Защищённые артефакты (не менять без retrain)

| Файл | Назначение |
| --- | --- |
| `models/model_registry.json` | champion metadata |
| `models/credit_scoring_nn.pt` | PyTorch weights |
| `models/credit_scoring_nn.onnx` | FP32 production ONNX |
| `models/credit_scoring_nn.quant.onnx` | INT8 experimental |
| `models/preprocessor.joblib` | preprocessor |
| `dvc.lock` | data pipeline lock |
