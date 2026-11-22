# Requirements Matrix — критерии проверки

Легенда статусов:

| Статус | Значение |
| --- | --- |
| `planned` | Запланировано, код ещё не реализован |
| `partial` | Частично есть в исходном проекте / каркасе |
| `implemented` | Реализовано в этом репозитории |
| `verified_local` | Проверено локально с артефактом/логом |
| `verified_ci` | Проверено в GitHub Actions |
| `skipped_no_env` | Намеренно пропущено: нет GPU/credentials/облака |
| `blocked` | Заблокировано до подтверждения пользователя |

Правило: статус `verified_*` ставится только при наличии реального доказательства (лог, JSON метрик, screenshot CI). Static validate ≠ cloud deploy.

---

## Этап 0. Аудит и архитектура

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 0.1 | Изучен исходный репозиторий | Описаны компоненты и baseline | `docs/implementation_plan.md` §1 | `implemented` |
| 0.2 | Определено переиспользование | Таблица reuse/adapt/drop | plan §1.3 | `implemented` |
| 0.3 | Совместимость с NN | Контракт raw→FE→preprocess→MLP | plan §1.4 | `implemented` |
| 0.4 | Архитектура нового проекта | Диаграмма + облачный выбор | plan §2 | `implemented` |
| 0.5 | План реализации | `docs/implementation_plan.md` | файл существует | `implemented` |
| 0.6 | Матрица требований | Этот файл | файл существует | `implemented` |
| 0.7 | Структура каталогов | Каркас директорий | `Get-ChildItem` | `implemented` |
| 0.8 | Зависимости и риски | Таблицы deps/risks | plan §4–6 | `implemented` |
| 0.9 | Оценка ресурсов | Таблица RAM/CPU/compose профили | plan §5 | `implemented` |
| 0.10 | План этапа 1 | Конкретные шаги и DoD | plan §8 | `implemented` |

---

## Этап 1. Модель и ONNX (5 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 1.1 | Новая NN на PyTorch | Бинарная классификация, тот же датасет/схема | `python -m src.nn.train_nn` + код модели | `verified_local` |
| 1.2 | Совместимая схема признаков | Те же `RAW_FEATURE_COLUMNS` + FE | unit tests features + schema | `verified_local` |
| 1.3 | Воспроизводимость | Фиксированные seeds/params; повторный прогон близок | params + лог seeds | `verified_local` |
| 1.4 | Сохранение модели и эксперимента | `.pt` + metadata/metrics JSON | наличие артефактов | `verified_local` |
| 1.5 | Конвертация в ONNX | Файл `.onnx` создан | `python -m src.nn.export_onnx` | `verified_local` |
| 1.6 | Валидация конвертации | Сравнение вероятностей PyTorch vs ORT | `artifacts/onnx_parity.json` | `verified_local` |
| 1.7 | Dynamic quantization / оптимизация | Quantized артефакт + обоснование | `python -m src.nn.quantize` | `verified_local` |
| 1.8 | Сравнение size/ROC-AUC/F1/latency/throughput/memory | Таблица в отчёте с измеренными значениями | `docs/model_benchmark.md` | `verified_local` |
| 1.9 | CPU benchmarks, несколько batch sizes | JSON с batch∈{1,16,64,256} | `artifacts/benchmark_cpu.json` | `verified_local` |
| 1.10 | Честный benchmark-отчёт | Нет выдуманных цифр; baseline RF не подменён | `docs/model_benchmark.md` | `verified_local` |
| 1.11 | GPU benchmark как отдельный сценарий | Auto-skip без GPU; без fake success | `artifacts/benchmark_gpu.json` SKIPPED | `verified_local` |
| 1.12 | Test не для подбора HP | Val только из train; test — финальная оценка | код split + отчёт | `verified_local` |
| 1.13 | Тесты этапа 1 | pytest на model/export/parity | `pytest` 34 passed | `verified_local` |

---

## Проектный этап 2. Inference API + Docker (выполнен 2026-11-22)

> Нумерация проектных этапов: после модели (этап 1) реализован serving API+Docker.
> Terraform из учебного «Этапа 2» остаётся следующим блоком (см. секцию ниже).

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| P2.1 | FastAPI ONNX FP32 serving | `/predict` на реальных артефактах | local+docker smoke | `verified_local` |
| P2.2 | Health live/ready | 200 / 503 | tests + smoke | `verified_local` |
| P2.3 | Batch + validation | limit 256, 422 on bad input | `tests/api` | `verified_local` |
| P2.4 | Prometheus `/metrics` | exporters present | smoke | `verified_local` |
| P2.5 | JSON logging | request_id/latency without PII | logs | `verified_local` |
| P2.6 | Multi-stage CPU Docker | no torch/CUDA | `docker/Dockerfile.api` | `verified_local` |
| P2.7 | Compose + volume artifacts | healthy container | `docker compose` | `verified_local` |
| P2.8 | API↔ONNX parity | integration tests | `test_integration_onnx.py` | `verified_local` |
| P2.9 | Docs | api/docker/stage2 reports | `docs/*` | `verified_local` |

---

## Учебный этап 2. Terraform / Cloud IaC (7 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 2.1 | Провайдер из списка задания | Выбран Yandex Cloud | docs + provider block | `planned` |
| 2.2 | Модуль network/VPC | Отдельный module | `infra/terraform/modules/network` | `planned` |
| 2.3 | Модуль Kubernetes | Managed K8s | `modules/kubernetes` | `planned` |
| 2.4 | Модуль storage | Object Storage | `modules/storage` | `planned` |
| 2.5 | Модуль monitoring | Cloud monitoring wiring / hooks | `modules/monitoring` | `planned` |
| 2.6 | Окружения staging/production | `envs/staging`, `envs/production` | дерево файлов | `planned` |
| 2.7 | CPU и GPU node groups | Оба описаны в module vars | tf vars/docs | `planned` |
| 2.8 | Security groups / сетевые политики | Ресурсы в network/k8s modules | код + docs | `planned` |
| 2.9 | Remote Terraform state | Backend Object Storage documented | `backend.tf` + docs | `planned` |
| 2.10 | Variables и outputs | Есть inputs/outputs | `variables.tf`/`outputs.tf` | `planned` |
| 2.11 | Безопасные секреты | Нет реальных секретов в Git; templates | grep + gitignore | `planned` |
| 2.12 | Статическая проверка до аккаунта | `terraform fmt -check`, `terraform validate` | локальные логи | `planned` |
| 2.13 | Нет apply без подтверждения | Apply не выполнен / задокументирован как blocked | отчёт этапа | `planned` / `blocked` до разрешения |

---

## Проектный этап 3А. Kubernetes local / kind (выполнен 2026-11-22)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| P3A.1 | kind cluster single-node | cluster Ready | `scripts/k8s_create.ps1` | `verified_local` |
| P3A.2 | Kustomize base + local overlay | `kubectl kustomize` | tests/k8s + render | `verified_local` |
| P3A.3 | Deployment + probes + securityContext | Ready Pod | deploy + smoke | `verified_local` |
| P3A.4 | Model delivery via models image + initContainer | artifacts in Pod, no hostPath | smoke ready | `verified_local` |
| P3A.5 | ConfigMap stage-2 env | threshold 0.5 / onnx paths | manifest | `verified_local` |
| P3A.6 | ClusterIP + port-forward inference | predict/batch/metrics | `k8s_smoke.ps1` | `verified_local` |
| P3A.7 | Rollout + rollback | undo works | `k8s_rollback.ps1` | `verified_local` |
| P3A.8 | Docs + validation report | real results | `docs/stage3a_validation_report.md` | `verified_local` |

---

## Этап 3. Docker и Kubernetes (8 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 3.1 | Multi-stage Dockerfile | Backend multi-stage | `docker/Dockerfile.api` | `verified_local` |
| 3.2 | Отдельные backend/frontend образы | Два Dockerfile | build обоих | `planned` |
| 3.3 | FastAPI inference | `/predict` + health | compose curl | `verified_local` |
| 3.4 | Минимальный frontend | Demo UI ходит в API | browser/curl | `planned` |
| 3.5 | DVC-интеграция артефактов | Документированный pull/repro в образе или entrypoint | docs + Dockerfile | `planned` |
| 3.6 | K8s Deployment rolling update | `strategy: RollingUpdate` | манифест + kind rollout | `verified_local` |
| 3.7 | Service | ClusterIP/LoadBalancer | манифест + port-forward | `verified_local` |
| 3.8 | Ingress | Ingress resource | манифест | `planned` |
| 3.9 | ConfigMap | Несекретная конфигурация | манифест | `verified_local` |
| 3.10 | Secret templates без реальных секретов | `*.secret.yaml.example` | `k8s/base/secret.example.yaml` | `implemented` |
| 3.11 | readiness/liveness probes | Оба probe | манифест + Ready Pod | `verified_local` |
| 3.12 | resource requests/limits | CPU/memory заданы | манифест | `verified_local` |
| 3.13 | Локальная проверка Docker Compose | `docker compose up` профиль api | локальный прогон | `verified_local` |

---

## Этап 4. CI/CD (5 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 4.1 | Последовательность build→test→deploy→monitor | Jobs/needs отражают цепочку | workflow YAML | `planned` |
| 4.2 | pytest | Job step | CI log | `planned` |
| 4.3 | black | `--check` | CI log | `planned` |
| 4.4 | flake8 | step | CI log | `planned` |
| 4.5 | Проверка схемы данных | validation step | CI log | `planned` |
| 4.6 | Docker build | build без push secrets обязательно | CI log | `planned` |
| 4.7 | Security scanning | Например Trivy/Hadolint | CI log | `planned` |
| 4.8 | Vulnerability scanning | Отчёт сканера | CI artifact/log | `planned` |
| 4.9 | Проверка K8s манифестов | kubeconform/kubectl dry-run | CI log | `planned` |
| 4.10 | Проверка Terraform | fmt/validate | CI log | `planned` |
| 4.11 | Staging deployment | Только при credentials | skipped или real | `planned` |
| 4.12 | Production deployment с подтверждением | `environment` approval / manual gate | workflow | `planned` |
| 4.13 | Проверка успешности rollout | `kubectl rollout status` при реальном deploy | CI log | `planned` |
| 4.14 | Безопасный skip без credentials | Job `skipped`, не fake success | CI conclusion | `planned` |

Опционально (не блокирует баллы по ПЗ): Blue-Green/Istio, Canary, auto-rollback — статус `planned` только если будет время; иначе явно `skipped` в отчёте.

---

## Этап 5. Observability (8 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 5.1 | Prometheus | scrape API `/metrics` | compose obs | `planned` |
| 5.2 | Метрики FastAPI | latency/throughput/error rate exporters | `/metrics` | `planned` |
| 5.3 | Grafana dashboards | JSON dashboards в репо | import/compose | `planned` |
| 5.4 | Loki + централизованные логи | API→Loki pipeline | compose | `planned` |
| 5.5 | Structured JSON logging | JSON fields в логах | sample log line | `planned` |
| 5.6 | Latency / throughput / error rate | На dashboard или метриках | Grafana/Prom | `planned` |
| 5.7 | Availability metrics | up / health probes | Prom rules | `planned` |
| 5.8 | Alerting rules | YAML alerts | `monitoring/alerts` | `planned` |
| 5.9 | Runbook | Типовые инциденты | `docs/runbooks/` | `planned` |

---

## Этап 6. Drift и управление моделями (7 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 6.1 | Evidently data drift | Отчёт HTML/JSON | скрипт + артефакт | `planned` |
| 6.2 | Model performance decay при метках | Метрики vs baseline при наличии y | код + отчёт | `planned` |
| 6.3 | Обоснованный approach к concept drift | Документ: когда можно/нельзя утверждать | docs | `planned` |
| 6.4 | Не утверждать concept drift без данных | Нет ложных claims | ревью отчётов | `planned` |
| 6.5 | Сравнение моделей | RF baseline vs NN/ONNX таблица | artifacts | `planned` |
| 6.6 | A/B routing двух версий | API router + конфиг долей | тесты API | `planned` |
| 6.7 | Учёт версий моделей | metadata/version registry файл или MLflow | артефакты | `planned` |
| 6.8 | Отчёты мониторинга | Сохранённые drift/performance reports | `artifacts/monitoring/` | `planned` |

Опционально: Seldon, shadow deployment — вне обязательного объёма.

---

## Этап 7. Airflow (5 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| 7.1 | DAG: проверка новых данных | Task существует | `airflow/dags/*.py` | `planned` |
| 7.2 | Валидация | Task | DAG | `planned` |
| 7.3 | Drift detection | Task | DAG | `planned` |
| 7.4 | Решение о переобучении | Branch/gate | DAG | `planned` |
| 7.5 | Переобучение | Task | DAG | `planned` |
| 7.6 | Оценка новой модели | Task | DAG | `planned` |
| 7.7 | Сравнение с production baseline | Task; fail если хуже порога | DAG | `planned` |
| 7.8 | Регистрация модели | Task | DAG | `planned` |
| 7.9 | Контролируемое развертывание | Без auto-promote плохой модели | код gate | `planned` |
| 7.10 | Retries / logging / failure handling | retries, on_failure | DAG params | `planned` |

---

## Документация (5 баллов)

| ID | Требование | Критерий приёмки | Как проверить | Статус |
| --- | --- | --- | --- | --- |
| D.1 | README.md | Установка, запуск, ограничения | файл | `planned` |
| D.2 | Архитектурная диаграмма | В `docs/architecture/` | файл | `planned` |
| D.3 | Инструкции Windows PowerShell | Команды в README/docs | файл | `planned` |
| D.4 | Docker Compose инструкции | docs | файл | `planned` |
| D.5 | Kubernetes инструкции | docs | файл | `planned` |
| D.6 | Terraform инструкции | docs + no-apply warning | файл | `planned` |
| D.7 | CI/CD инструкции | docs | файл | `planned` |
| D.8 | Описание экспериментов | docs/metrics | файл | `planned` |
| D.9 | Benchmark-отчёт | Только измеренные данные | `docs/model_benchmark.md` | `verified_local` |
| D.10 | Описание мониторинга | docs | файл | `planned` |
| D.11 | Runbook | docs/runbooks | файл | `planned` |
| D.12 | Таблица соответствия заданию | Этот файл, обновлять статусы | ревью | `partial` (каркас) |

---

## Глобальные ограничения проекта

| ID | Ограничение | Критерий | Статус контроля |
| --- | --- | --- | --- |
| G.1 | Не выдумывать метрики/deploy | Только measured/skipped | процесс |
| G.2 | Не менять baseline RF метрики без переобучения | `artifacts/baseline_metrics.json` immutable note | процесс |
| G.3 | Не использовать test для HP search | Code review split | процесс |
| G.4 | Нет реальных секретов в Git | secret scanning / review | процесс |
| G.5 | Нет `terraform apply` без подтверждения | blocked by default | процесс |
| G.6 | Static check ≠ cloud success | Явные статусы в отчётах | процесс |
| G.7 | Нет заглушек как «готово» | DoD каждого этапа | процесс |
| G.8 | Учёт 8 GB RAM / CPU-only | Compose профили, torch CPU | процесс |

---

## Сводка покрытия баллов (план)

| Этап | Макс. баллов | Текущая готовность |
| --- | ---: | --- |
| Подготовка модели | 5 | ~100% локально verified (этап 1) |
| Cloud Infrastructure | 7 | 0% |
| Контейнеризация и K8S | 8 | ~40% (API+Docker; K8s pending) |
| CI/CD | 5 | 0% |
| Мониторинг | 8 | 0% |
| Мониторинг дрифта | 7 | 0% |
| Автоматизация | 5 | 0% |
| Документация | 5 | ~10% (план + матрица) |
| **Итого** | **50** | **этап 0 завершён** |
