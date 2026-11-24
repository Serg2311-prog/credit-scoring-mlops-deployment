# Requirements Matrix — критерии проверки

**Актуализация:** 2026-11-22 (перед сдачей).
**Согласовано с:** [`README.md`](../README.md), отчётами `docs/stage*_*.md`, коммитом [`65de3ad`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/commit/65de3ad680a2fc7f3fcbe374aeb07f485d773b63).

Нумерация ниже — **учебная** (как в README): 0 → 1 → 2 (Terraform) → 3 (Docker/K8s/DVC) → 4 → 5 → 6 → 7.
История «проектных» подэтапов (API+Docker как P2, kind как P3A) сохранена внутри соответствующих секций.

Легенда статусов:

| Статус | Значение |
| --- | --- |
| `planned` | Запланировано, код ещё не реализован |
| `partial` | Реализовано частично / есть только каркас или документация |
| `implemented` | Реализовано в этом репозитории (код/манифесты/docs) |
| `verified_local` | Проверено локально с артефактом/логом/отчётом |
| `verified_ci` | Проверено в GitHub Actions (успешный run) |
| `partial_verified` | Частично проверено (код есть, полный E2E/облако не гонялось) |
| `not_executed` | Намеренно не выполнялось (cloud apply, prod deploy, тяжёлый E2E) |
| `skipped_no_env` | Пропущено из‑за отсутствия среды (GPU/credentials/облако) |
| `blocked` | Заблокировано до явного подтверждения |

Правило: статус `verified_*` ставится только при наличии реального доказательства (лог, JSON метрик, CI run).
`terraform validate` / static checks ≠ cloud deploy. Static Docker build ≠ Airflow Docker E2E.

---

## Этап 0. Аудит и архитектура

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 0.1 | Изучен исходный репозиторий | Описаны компоненты и baseline | `docs/implementation_plan.md` §1 | `verified_local` |
| 0.2 | Определено переиспользование | Таблица reuse/adapt/drop | plan §1.3 | `verified_local` |
| 0.3 | Совместимость с NN | Контракт raw→FE→preprocess→MLP | plan §1.4 + код | `verified_local` |
| 0.4 | Архитектура нового проекта | Диаграмма + облачный выбор | plan §2, `docs/architecture/overview.md` | `verified_local` |
| 0.5 | План реализации | `docs/implementation_plan.md` | файл существует | `verified_local` |
| 0.6 | Матрица требований | Этот файл | файл существует | `verified_local` |
| 0.7 | Структура каталогов | Каркас директорий | дерево репозитория | `verified_local` |
| 0.8 | Зависимости и риски | Таблицы deps/risks | plan §4–6 | `verified_local` |
| 0.9 | Оценка ресурсов | Таблица RAM/CPU/compose профили | plan §5 | `verified_local` |
| 0.10 | План этапа 1 | Конкретные шаги и DoD | plan §8 (исторический план; этап 1 выполнен) | `verified_local` |

---

## Этап 1. Модель и ONNX (5 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 1.1 | Новая NN на PyTorch | Бинарная классификация, тот же датасет/схема | `python -m src.nn.train_nn` + код модели | `verified_local` |
| 1.2 | Совместимая схема признаков | Те же `RAW_FEATURE_COLUMNS` + FE | unit tests features + schema | `verified_local` |
| 1.3 | Воспроизводимость | Фиксированные seeds/params | `params.yaml` + отчёт | `verified_local` |
| 1.4 | Сохранение модели и эксперимента | `.pt` + metadata/metrics JSON | артефакты / metadata | `verified_local` |
| 1.5 | Конвертация в ONNX | Файл `.onnx` создан | `python -m src.nn.export_onnx` | `verified_local` |
| 1.6 | Валидация конвертации | PyTorch vs ORT | `artifacts/onnx_parity.json` | `verified_local` |
| 1.7 | Dynamic quantization | Quantized артефакт + обоснование | `python -m src.nn.quantize` | `verified_local` |
| 1.8 | Сравнение size/ROC-AUC/F1/latency/… | Измеренные значения | `docs/model_benchmark.md` | `verified_local` |
| 1.9 | CPU benchmarks, несколько batch sizes | JSON batch∈{1,16,64,256} | `artifacts/benchmark_cpu.json` | `verified_local` |
| 1.10 | Честный benchmark-отчёт | RF baseline не подменён (ROC-AUC **0.7771**; MLP **0.7742**) | `docs/model_benchmark.md` | `verified_local` |
| 1.11 | GPU benchmark | Auto-skip без GPU | `artifacts/benchmark_gpu.json` SKIPPED | `verified_local` |
| 1.12 | Test не для подбора HP | Val только из train | код split + отчёт | `verified_local` |
| 1.13 | Тесты этапа 1 | pytest model/export/parity | suite в полном pytest | `verified_local` |

Отчёт: [`docs/stage1_audit_report.md`](stage1_audit_report.md), [`docs/model_benchmark.md`](model_benchmark.md).

---

## Этап 2. Terraform / Yandex Cloud IaC (код без apply)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 2.1 | Провайдер из списка задания | Yandex Cloud | docs + provider block | `implemented` |
| 2.2 | Модуль network/VPC | Отдельный module | `infra/terraform/modules/network` | `implemented` |
| 2.3 | Модуль Kubernetes | Managed K8s | `modules/kubernetes` | `implemented` |
| 2.4 | Модуль storage | Object Storage | `modules/storage` | `implemented` |
| 2.5 | Модуль monitoring | Cloud monitoring notes | `modules/monitoring` | `implemented` |
| 2.6 | Окружения staging/production | `environments/*` | дерево файлов | `implemented` |
| 2.7 | CPU/GPU node groups | CPU always; GPU `enable_gpu_node_group=false` (schema-verified) | modules/kubernetes + tests | CPU `implemented`/`verified_static`; GPU IaC `implemented`, cloud `not_executed` |
| 2.8 | Security groups / сетевые политики | SG + CALICO + K8s NP | код + tests; NP traffic | SG `verified_static`; NP enforcement local **`blocked`** (kindnet/RAM) |
| 2.9 | Remote Terraform state | Backend + `backend.hcl.example`; lockfile NOT_VERIFIED on Yandex | examples + Block 6.1 notes | example `implemented`; live remote `not_executed` |
| 2.10 | Variables и outputs | Есть inputs/outputs (+ GPU outputs) | `variables.tf`/`outputs.tf` | `implemented` |
| 2.11 | Безопасные секреты | Нет реальных секретов в Git | grep + gitignore | `verified_local` |
| 2.12 | Статическая проверка до аккаунта | `terraform fmt -check`, `validate` | Block 6 report + CI Infrastructure | `verified_local` / prior `verified_ci` |
| 2.13 | Нет apply без подтверждения | **Cloud apply не выполнялся** | Block 6 + README | `not_executed` (apply) / контроль `verified_local` |

Отчёты: [`docs/stage2_infrastructure_completion_report.md`](stage2_infrastructure_completion_report.md), [`docs/stage3b_validation_report.md`](stage3b_validation_report.md), [`docs/terraform_infrastructure.md`](terraform_infrastructure.md).

**Явно:** production / staging в Yandex Cloud **не развёрнуты**. `terraform apply` = `not_executed`.

---

## Этап 3. Docker, Kubernetes, DVC

### 3.A История: Inference API + Docker (проектный подэтап P2, 2026-11-22)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| P2.1 | FastAPI ONNX FP32 serving | `/predict` | local+docker smoke | `verified_local` |
| P2.2 | Health live/ready | 200 / 503 | tests + smoke | `verified_local` |
| P2.3 | Batch + validation | limit 256, 422 | `tests/api` | `verified_local` |
| P2.4 | Prometheus `/metrics` | exporters | smoke + tests | `verified_local` |
| P2.5 | JSON logging | request_id/latency without PII | logs | `verified_local` |
| P2.6 | Multi-stage CPU Docker | no torch/CUDA in runtime image | `docker/Dockerfile.api` | `verified_local` |
| P2.7 | Compose + volume artifacts | healthy container | `docker compose` | `verified_local` |
| P2.8 | API↔ONNX parity | integration tests | `tests/api/test_integration_onnx.py` | `verified_local` |
| P2.9 | Docs | api/docker reports | `docs/api_contract.md`, `docs/docker_deployment.md` | `verified_local` |

Отчёт: [`docs/stage2_validation_report.md`](stage2_validation_report.md).

### 3.B История: Kubernetes local / kind (проектный подэтап P3A, 2026-11-22)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| P3A.1 | kind cluster single-node | cluster Ready | `scripts/k8s_create.ps1` | `verified_local` |
| P3A.2 | Kustomize base + local overlay | `kubectl kustomize` | tests/k8s + render | `verified_local` |
| P3A.3 | Deployment + probes + securityContext | Ready Pod | deploy + smoke | `verified_local` |
| P3A.4 | Model delivery via models image + initContainer | artifacts in Pod | smoke ready | `verified_local` |
| P3A.5 | ConfigMap | threshold 0.5 / onnx paths | manifest | `verified_local` |
| P3A.6 | ClusterIP + port-forward | predict/batch/metrics | `scripts/k8s_smoke.ps1` | `verified_local` |
| P3A.7 | Rollout + rollback | undo works | `scripts/k8s_rollback.ps1` | `verified_local` |
| P3A.8 | Docs + validation report | real results | `docs/stage3a_validation_report.md` | `verified_local` |

### 3.C Сводные требования этапа 3 (учебная нумерация)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 3.1 | Multi-stage Dockerfile | Backend multi-stage | `docker/Dockerfile.api` | `verified_local` |
| 3.2 | Отдельные backend/frontend образы | API + frontend Dockerfiles | `Dockerfile.frontend` + compose/k8s | `verified_local` |
| 3.3 | FastAPI inference | `/predict` + health | compose / Ingress E2E | `verified_local` |
| 3.4 | Минимальный frontend | Demo UI → API | `frontend/` + compose `:8081` | `verified_local` |
| 3.5 | DVC-интеграция артефактов | pipeline + local remote + Docker | `dvc.yaml` / `Dockerfile.dvcdata` | `verified_local` (synthetic demo; не UCI raw) |
| 3.6 | K8s Deployment rolling update | `RollingUpdate` | манифест + kind | `verified_local` |
| 3.7 | Service | ClusterIP API+frontend | манифесты | `verified_local` |
| 3.8 | Ingress | Ingress + routing E2E | controller port-forward | `verified_local` (host `:8080` kind recreate = `partial`) |
| 3.9 | ConfigMap | Несекретная конфигурация | манифест | `verified_local` |
| 3.10 | Secret templates | `*.example` без реальных секретов | `k8s/base/secret.example.yaml` | `implemented` |
| 3.11 | readiness/liveness probes | Оба probe | Ready Pods | `verified_local` |
| 3.12 | resource requests/limits | CPU/memory | манифест | `verified_local` |
| 3.13 | Docker Compose локально | API+frontend | `docker compose up` | `verified_local` |
| 3.14 | NetworkPolicy | deny/allow manifests | applied + script | `partial_verified` (kindnet **не enforce**) |

**DVC:** synthetic demo pipeline verified; production ONNX не в DVC outs; remote local gitignored.

---

## Этап 4. CI/CD (5 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 4.1 | Последовательность build→test→deploy→monitor | `ci-cd.yml` gates **5** CI → publish → deploy | YAML + tests | `implemented` / orchestrator `verified_static`; hosted CD `not_executed` |
| 4.2 | pytest | Job step | `ci-python.yml` | `verified_ci` |
| 4.3 | black | `--check` | `ci-python.yml` | `verified_ci` |
| 4.4 | flake8 | step | `ci-python.yml` | `verified_ci` |
| 4.5 | Проверка схемы данных | validation в pytest | CI Python | `verified_ci` |
| 4.6 | Docker build | build + optional GHCR push by SHA | `ci-docker.yml` / `ci-cd.yml` | build `verified_ci`; GHCR push `not_executed` (no commit/push this block) |
| 4.7 | Security scanning | Trivy в CI Docker (+ pre-push in orchestrator) | CI Docker | `verified_ci` |
| 4.8 | Vulnerability scanning | Отчёт сканера / job success | CI Docker | `verified_ci` |
| 4.9 | Проверка K8s манифестов | kustomize / kubeconform + staging/prod overlays | `ci-kubernetes.yml` | `verified_ci` + overlays `verified_static` |
| 4.10 | Проверка Terraform | fmt/validate | `ci-infrastructure.yml` | `verified_ci` |
| 4.11 | Staging deployment | Fail-closed `mode=deploy` + opt-in auto; kind CD demo | `local_cd_verify.ps1` / workflows | kind demo `verified_local`; cloud apply `not_executed` |
| 4.12 | Production deployment | Provenance via `staging-release.json` + Environment | workflow + kind prod-demo | workflow `implemented`/`verified_static`; kind promote `verified_local`; cloud `not_executed` |
| 4.13 | Проверка rollout | kind CD + smoke_http | local CD | `verified_local` |
| 4.14 | Fail-closed vs validation | `mode=deploy` fails without secrets/vars; `validation`/`publish` separate | `ci-cd` / `cd-production` + tests | `implemented` / `verified_static` |

На коммите **`65de3ad`** SUCCESS: CI Python, CI Docker, CI Infrastructure, CI Kubernetes, CI Airflow DAG
(см. [`README.md`](../README.md), [`docs/stage4_validation_report.md`](stage4_validation_report.md) для более ранней истории kind/RC).

---

## Этап 5. Observability (8 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 5.1 | Prometheus | scrape API `/metrics` | compose + `scripts/observability/check.ps1` | `verified_local` |
| 5.2 | Метрики FastAPI | latency/throughput/error/inference | `/metrics` + tests | `verified_local` |
| 5.3 | Grafana dashboards | JSON + provisioning | `monitoring/grafana/` | `verified_local` |
| 5.4 | Loki + централизованные логи | Alloy → Loki | Explore Loki | `verified_local` |
| 5.5 | Structured JSON logging | timestamp/level/service/request_id | API stdout | `verified_local` |
| 5.6 | Latency / throughput / error rate | Dashboards | Grafana | `verified_local` |
| 5.7 | Availability metrics | `up` + `credit_scoring_model_ready` | Prom + alerts | `verified_local` |
| 5.8 | Alerting rules | YAML + Alertmanager | `monitoring/prometheus/alerts.yml` | `verified_local` |
| 5.9 | Runbook | Типовые инциденты | `docs/stage5_runbook.md` | `implemented` |

Облачный observability в Yandex Cloud: `not_executed`.
Отчёт: [`docs/stage5_validation_report.md`](stage5_validation_report.md).

---

## Этап 6. Drift и управление моделями (7 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 6.1 | Evidently data drift | Отчёт HTML/JSON | `python -m src.monitoring.cli` / tests | `verified_local` |
| 6.2 | Model performance decay при метках | Метрики vs reference | `concept-drift` + tests | `verified_local` |
| 6.3 | Approach к concept drift | Когда можно/нельзя утверждать | `docs/stage6_runbook.md` | `implemented` |
| 6.4 | Не утверждать concept drift без данных | Только signal | `confirmed_concept_drift=False` | `verified_local` |
| 6.5 | Сравнение моделей | Offline A/B + RF/NN benchmark | CLI + `docs/model_benchmark.md` | `verified_local` |
| 6.6 | A/B routing двух версий | Router + доли (AB off by default) | `ab_router` + tests | `verified_local` |
| 6.7 | Учёт версий моделей | `models/model_registry.json` | demo / registry | `verified_local` |
| 6.8 | Отчёты мониторинга | drift/performance reports | `artifacts/monitoring/` (gitignored) | `verified_local` |

Опционально: Seldon, shadow deployment — вне обязательного объёма.
Отчёт: [`docs/stage6_validation_report.md`](stage6_validation_report.md).

---

## Этап 7. Airflow Retraining (5 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 7.1 | DAG: проверка новых данных | Task + Docker DagRun `new_data` | E2E A2/A2b + fingerprint baseline | `verified_local` / parse `verified_ci` |
| 7.2 | Валидация | Task + unit + Docker E2E | `data_validation` + E2E A | `verified_local` |
| 7.3 | Drift detection | Trigger `data_drift` | unit + Docker E2E B/D | `verified_local` |
| 7.4 | Решение о переобучении | Branch skip vs train + cron schedule | Docker E2E A/D + scheduler `scheduled__*` | `verified_local` |
| 7.5 | Переобучение | Candidate train в run dir | Docker E2E A / A2 (logistic) | `verified_local` |
| 7.6 | Оценка новой модели | Holdout metrics | E2E `evaluation.json` | `verified_local` |
| 7.7 | Сравнение с production baseline | Same-holdout ONNX champion vs candidate | E2E `champion_status=scored_on_holdout`; else `needs_review` | `verified_local` |
| 7.8 | Регистрация модели | Atomic registry, **no champion overwrite** | dry_run registry + hashes | `verified_local` |
| 7.9 | Контролируемое развертывание | **`auto_promote=false`** | E2E report + hashes | `verified_local` |
| 7.10 | Retries / failure handling | skip branch + missing-input fail | Docker E2E D/E | `verified_local` |

### Ограничения этапа 7 (обязательно учитывать)

| Тема | Статус |
| --- | --- |
| Движок retraining без Airflow (Windows CLI/pytest) | `verified_local` (pytest suite green) |
| DAG import/parse в Linux CI (`ci-airflow-dag.yml`) | `verified_ci` |
| Полный Airflow Docker E2E (`e2e_docker.ps1`, A/A2/B/C/D/E + scheduler proof) | **`verified_local`** — `docs/stage7_airflow_e2e_report.md` |
| Staff cron `0 3 * * 1` + E2E overlay `RETRAIN_SCHEDULE=None` | **`verified_local`** |
| Airflow Docker E2E в GitHub Actions | **`not_executed`** (не claimed as `verified_ci`) |
| Airflow в Windows `.venv` | не устанавливается (by design) |
| Automatic promotion challenger → production | **запрещено** (`auto_promote=false`) |
| Default candidate backend | logistic + существующий preprocessor; MLP optional/heavier |

Отчёт: [`docs/stage7_validation_report.md`](stage7_validation_report.md), [`docs/stage7_runbook.md`](stage7_runbook.md).

---

## Документация (5 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| D.1 | README.md | Установка, запуск, ограничения, этапы 0–7 | [`README.md`](../README.md) | `verified_local` |
| D.2 | Архитектурная диаграмма / обзор | `docs/architecture/` | `overview.md` | `implemented` |
| D.3 | Инструкции Windows PowerShell | Команды в README/docs | README + runbooks | `verified_local` |
| D.4 | Docker Compose инструкции | docs | `docs/docker_deployment.md` | `verified_local` |
| D.5 | Kubernetes инструкции | docs | `docs/kubernetes_local_deployment.md` | `verified_local` |
| D.6 | Terraform инструкции | docs + no-apply warning | `docs/terraform_infrastructure.md` | `verified_local` |
| D.7 | CI/CD инструкции | docs | `docs/cicd_pipeline.md` | `verified_local` |
| D.8 | Описание экспериментов / метрик | docs + artifacts notes | `docs/model_benchmark.md` | `verified_local` |
| D.9 | Benchmark-отчёт | Только измеренные данные | `docs/model_benchmark.md` | `verified_local` |
| D.10 | Описание мониторинга | docs | `docs/architecture/observability.md` | `implemented` |
| D.11 | Runbooks | stage 5–7 | `docs/stage5_runbook.md` … `stage7_runbook.md` | `implemented` |
| D.12 | Таблица соответствия заданию | Этот файл, актуальные статусы | ревью | `verified_local` |

---

## Глобальные ограничения проекта

| ID | Ограничение | Критерий | Статус контроля |
| --- | --- | --- | --- |
| G.1 | Не выдумывать метрики/deploy | Только measured/skipped/not_executed | процесс |
| G.2 | Не менять baseline RF без переобучения | `artifacts/baseline_metrics.json` immutable | процесс |
| G.3 | Не использовать test для HP search | Code review split | процесс |
| G.4 | Нет реальных секретов в Git | review / gitignore | процесс |
| G.5 | Нет `terraform apply` без подтверждения | **apply = not_executed** | `verified_local` |
| G.6 | Static check ≠ cloud success | Явные статусы в отчётах | процесс |
| G.7 | Нет заглушек как «готово» | DoD каждого этапа | процесс |
| G.8 | Учёт 8 GB RAM / CPU-only | Compose профили, torch CPU | процесс |
| G.9 | Нет auto-promote модели | Stage 6/7 registry + gates | `verified_local` |
| G.10 | DVC remote/pipeline не выдавать за готовый | Нет `dvc.yaml` → `partial` | процесс |
| G.11 | Airflow Docker E2E не заявлять без прогона | `verified_local` after `e2e_docker.ps1` | `docs/stage7_airflow_e2e_report.md` |

---

## Сводка покрытия (актуально)

| Учебный этап | Содержание | Готовность кода | Проверка |
| --- | --- | --- | --- |
| 0 | Аудит / план / матрица | Готово | `verified_local` |
| 1 | MLP / ONNX / benchmark | Готово | `verified_local` |
| 2 | Terraform YC | Код готов | validate local/CI; **apply `not_executed`** |
| 3 | Docker / kind / K8s / DVC / frontend | Frontend+Ingress+DVC verified locally | NP enforcement kindnet `partial`; CI на новых Dockerfile — `not_executed` до push |
| 4 | CI/CD | Готово | **5× SUCCESS на `65de3ad`**; prod deploy `not_executed` |
| 5 | Observability | Готово локально | `verified_local`; cloud obs `not_executed` |
| 6 | Drift / A/B | Готово | `verified_local` |
| 7 | Airflow retraining | Engine+DAG+compose+E2E | local Docker A/A2/B/C/D/E + scheduler proof `verified_local`; CI parse `verified_ci`; **no auto-promote** |
| Docs | README + runbooks + matrix | Готово | `verified_local` |

**Итоговая формулировка для сдачи:** этапы **0–7 реализованы в репозитории** с честным разделением `verified_local` / `verified_ci` / `partial` / `not_executed`. Cloud production **не утверждается**. Airflow Docker E2E — **`verified_local`** (не `verified_ci`).
