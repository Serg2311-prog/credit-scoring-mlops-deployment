# Итоговый отчёт проекта

**Название:** Промышленное развёртывание кредитной скоринговой системы с полным MLOps-циклом
**Репозиторий:** `credit-scoring-mlops-deployment`
**Документационный baseline:** commit `0df191a`
**Дата Block 9:** 2026-11-25

Официальную оценку (из 50) выставляет ментор. Ниже — фактические результаты существующих экспериментов.

---

## 1. Аннотация

Реализован воспроизводимый MLOps-контур кредитного скоринга: PyTorch MLP → ONNX FP32 serving → Docker/kind → Terraform IaC (без apply) → GitHub Actions → Prometheus/Grafana/Loki → Evidently drift + A/B → Airflow retraining без auto-promote. Качество MLP на holdout **не превосходит** исторический RF baseline; это зафиксировано явно.

## 2. Постановка задачи

Перенести скоринговую модель из учебного контура в промышленно-подобный контур доставки и эксплуатации согласно ТЗ этапов 1–7 + документация, без фиктивных метрик и без скрытых ограничений.

## 3. Исходные данные

- Датасет: UCI Credit Card Default (Taiwan), бинарный target default payment.
- Схема: raw features → FE → `preprocessor.joblib` → модель.
- В Git нет персональных данных клиентов; CI использует synthetic serving artifacts.
- Версионирование данных: DVC (`dvc.yaml` / `dvc.lock`).

## 4. Базовая ML-модель

| Модель | Test ROC-AUC | Источник |
| --- | ---: | --- |
| RandomForest baseline | **0.7771** | `artifacts/baseline_metrics.json` |

RF **не** заменяется и **не** маскируется под NN.

## 5. PyTorch MLP

- Архитектура MLP, обучение с early stopping по **val** ROC-AUC (val из train).
- Test ROC-AUC **0.7742**; Precision/Recall/F1/Accuracy зафиксированы в `docs/model_benchmark.md`.
- MLP уступает RF по holdout quality — отражено в отчётах без «улучшательства».

## 6. ONNX и quantization

| Артефакт | Роль | Test ROC-AUC (holdout) |
| --- | --- | ---: |
| `credit_scoring_nn.onnx` | production champion FP32 | **0.7742** (parity с PyTorch) |
| `credit_scoring_nn.quant.onnx` | experimental INT8 | **0.7736** (не auto-champion) |

Dynamic quantization уменьшает размер; вероятности отклоняются от FP32; доля смены решений зафиксирована в benchmark (~2.18%). Quant **не** объявлен лучшим автоматически.

## 7. CPU/GPU benchmark

**CPU (model_only):** batch ∈ {1,8,32,64,128}, thread probe — `results/block7/`.
**HTTP load:** отдельный synthetic API load — не смешивать с model-only throughput.
**GPU:** Colab Tesla T4 hardened evidence — `results/block7/colab/hardened/` (`VERIFIED_GPU`).
**Не выполнялись:** GPU INT8, GPU HTTP load test.
Локально GPU может быть `BLOCKED_NO_GPU`.

## 8. API и frontend

- FastAPI: `/health/live`, `/health/ready`, `/predict`, `/predict/batch`, `/model/info`, `/metrics`.
- Structured JSON logs + `X-Request-ID`.
- Frontend: nginx UI на `:8081`, proxy `/api` → API.
- Контракт: `docs/api_contract.md`.

## 9. Docker и Kubernetes

- Multi-stage CPU images: API, frontend, models, dvcdata.
- Compose smoke verified.
- kind + Kustomize + Ingress verified locally.
- NetworkPolicy manifests present; **enforcement на kindnet не подтверждён runtime**.
- Cloud K8s deploy **NOT_EXECUTED**.

## 10. Terraform

- Модули Yandex Cloud: network, iam, kubernetes, registry, storage, monitoring.
- staging/production roots, separate state keys в examples.
- `fmt`/`validate` (`-backend=false`) — VERIFIED_LOCAL / CI.
- **`terraform apply` не выполнялся**; live remote state **не** проверялся.
- GPU node group schema есть, default **off**.

## 11. CI/CD

- Gates: Python (pytest/black/flake8), Docker+Trivy, Terraform validate, kubeconform, Airflow DAG import.
- Orchestrator `ci-cd.yml`; CD staging dry-run; production promote digests only.
- Hosted cloud deploy / GHCR publish без credentials — по политике NOT_EXECUTED где применимо.
- На проверенных прогонах: 5/5 SUCCESS (см. `docs/cicd_pipeline.md` / stage4 reports).

## 12. Monitoring and alerting

- Prometheus: API metrics + cAdvisor (Desktop: без container `name` labels).
- Grafana dashboards provisioned.
- Alloy → Loki; Loki Ruler log alerts; Alertmanager → local webhook.
- Metric alert `APIDown` и log alert `APIErrorLogsDetected`: firing → resolved (Block 8/8.1).
- E2E log probe — отдельный test-only сервис, не production API route.

## 13. Data drift, model degradation и concept drift

- Evidently data drift (target исключён из feature drift).
- Performance degradation = multi-metric **signal** на labeled cohort.
- `confirmed_concept_drift` не выставляется только из падения ROC-AUC.
- Controlled synthetic experiment A–D (Block 8.1) демонстрирует известное изменение P(Y|X) при неизменном X — это **не** доказательство production concept drift.

## 14. Online A/B

- Default: `AB_ENABLED=false`.
- Offline A/B: same-holdout compare, `auto_promote=false`.
- Online: isolated compose; champion FP32 + **existing** quant ONNX as experimental challenger.
- ≥1000 assignment IDs; HTTP both branches; stable hash assignment; Prometheus `ml_ab_*`.
- Synthetic traffic only.

## 15. Airflow retraining

- DAG: new data / validation / drift / quality triggers → candidate train → eval.
- Docker E2E VERIFIED_LOCAL (`docs/stage7_airflow_e2e_report.md`).
- Decision layer на monitoring artifacts: skip / trigger / unavailable.
- **auto_promote=false**; production registry не переписывается автоматически.

## 16. Безопасность

- Trivy in CI; no secrets in Git; `.env.example` only.
- Terraform credentials via env, not CLI `-backend-config=access_key/secret_key`.
- Probe removed from production API; evidence sanitized (Block 8.1).
- `_raw_encoding_backup/` gitignored.

## 17. Тестирование

- `pytest -m "not k8s and not e2e"`: **231 passed, 2 skipped** (Block 8.1 на чистом дереве).
- Markers отделяют k8s/e2e.
- Black/Flake8 в CI scope — PASS.

## 18. Воспроизводимость

- Fixed seeds/params (`params.yaml`).
- SHA256 gate на 6 production artifacts.
- DVC lock; CI synthetic artifacts.
- GPU evidence + Block 8 evidence сохраняются без renormalize.

## 19. Ограничения

1. Terraform apply / paid cloud resources — не выполнялись.
2. Live remote state — не проверялся.
3. Cloud staging/production deploy — не выполнялся.
4. GPU node group в облаке — не запускалась.
5. NetworkPolicy enforcement (kind) — не runtime-подтверждён.
6. GPU INT8 и GPU HTTP load — не выполнялись.
7. Online A/B challenger = quantized ONNX (эксперимент).
8. cAdvisor Docker Desktop — ограничение labels.
9. Airflow — локальный Docker E2E, не managed cloud.
10. Seldon / shadow / Istio / Redis geo — OPTIONAL, не реализованы.
11. Synthetic/controlled experiments ≠ production client traffic / real concept drift proof.

## 20. Заключение

Проект закрывает обязательные этапы ТЗ с локально и/или CI-подтверждёнными доказательствами и честно документированными gaps по облаку и optional пунктам. Документация Block 9 связывает критерии, код и evidence для проверки ментором без повторного запуска дорогих экспериментов.
