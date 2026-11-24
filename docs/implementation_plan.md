# Implementation Plan — credit-scoring-mlops-deployment

**Дата аудита (этап 0):** 2026-11-22
**Актуализация перед сдачей:** 2026-11-22
**Исходный репозиторий:** https://github.com/Serg2311-prog/credit-default-prediction
**Локальная копия для аудита:** `../_source_audit/credit-default-prediction-main`

### Текущий статус репозитория (не путать с аудитом исходника ниже)

| Утверждение | Факт |
| --- | --- |
| Этапы 0–7 | **Реализованы** в этом репозитории (см. [`README.md`](../README.md)) |
| Коммит подтверждения этапа 7 | [`65de3ad`](https://github.com/Serg2311-prog/credit-scoring-mlops-deployment/commit/65de3ad680a2fc7f3fcbe374aeb07f485d773b63) |
| GitHub Actions на `65de3ad` | 5× SUCCESS (Python, Docker, Infrastructure, Kubernetes, Airflow DAG) |
| Локальный pytest (этап 7) | **137 passed, 1 skipped** |
| `terraform apply` / YC production | **`not_executed`** |
| Полный Airflow Docker E2E | **`verified_local`** (Block 4.1: cron + scheduler DagRun + `new_data` + same-holdout gate; `docs/stage7_airflow_e2e_report.md`; CI compose E2E not claimed) |
| CI/CD staging/production (Block 5 / 5.1) | Overlays + orchestrator/production with 5-CI gate, opt-in auto staging, staging-release provenance, fail-closed modes **implemented** / **verified_static**; kind CD **`verified_local`**; GHCR/cloud **`not_executed`** (`docs/stage4_cicd_completion_report.md`) |
| Terraform / cloud infra (Block 6) | GPU opt-in NG + remote-state docs + validate **`verified_static`/`verified_local`**; apply / live remote / GPU cloud **`not_executed`**; NP enforcement **`blocked`** (kindnet/RAM) — `docs/stage2_infrastructure_completion_report.md` |
| Auto-promote модели | **запрещён** (`auto_promote=false`) |
| Рабочий DVC pipeline (`dvc.yaml` + local remote) | **есть** (synthetic demo; см. `docs/stage3_completion_report.md`) |

Секции §1 и §9 ниже сохраняют **исторический** аудит исходного проекта и проверки этапа 0.
Актуальная матрица статусов: [`docs/requirements_matrix.md`](requirements_matrix.md).

---

## 1. Результаты аудита исходного проекта

> Исторический снимок на момент этапа 0: что было в **credit-default-prediction**, а не текущее состояние этого репозитория.

### 1.1. Что уже реализовано и проверено в исходнике

| Компонент | Состояние | Примечание |
| --- | --- | --- |
| UCI Default of Credit Card Clients | Есть | CSV не в Git; `dvc.lock` фиксирует checksum |
| Pandera-валидация | Есть | `src/data/validation.py`, синтетика + негативный AGE |
| Feature Engineering | Есть | row-wise агрегаты, без leakage |
| Sklearn Pipeline | Есть | FeatureEngineer → impute/scale/OHE → model |
| LR / RF / GB + search | Есть | выбор по CV ROC-AUC на train |
| MLflow Tracking | Есть | локальный `mlruns` |
| DVC pipeline | Есть | prepare → train → evaluate; **remote не настроен** |
| FastAPI `/predict` | Есть | сырые 23 признака клиента |
| Docker / Compose | Есть | single-stage, только API |
| Pytest + flake8 + black | Есть | |
| GitHub Actions CI | Есть | quality only, без deploy |
| PSI monitoring | Есть | train vs sample(test); не Evidently |
| Frontend | Нет | |
| ONNX / PyTorch | Нет | |
| Terraform / K8s manifests | Нет | |
| Prometheus / Grafana / Loki | Нет | |
| Airflow | Нет | |
| A/B routing | Нет | |

### 1.2. Зафиксированный baseline (не изменять без реального переобучения)

Production baseline исходного проекта — `RandomForestClassifier`
(`n_estimators=80`, `max_depth=10`, `min_samples_leaf=1`, `class_weight="balanced"`):

| Метрика | Значение |
| --- | ---: |
| CV ROC-AUC | 0.7837 |
| Test ROC-AUC | 0.7771 |
| PR-AUC | 0.5536 |
| Precision | 0.4786 |
| Recall | 0.6081 |
| F1 | 0.5357 |
| Accuracy | 0.7668 |

Эти числа копируются в документацию нового проекта как **исторический baseline sklearn**.
Метрики новой NN будут измеряться отдельно и **не подменяют** baseline.

### 1.3. Компоненты для переиспользования

**Переиспользовать почти без изменений (скопировать и адаптировать импорты/пути):**

- `src/schema.py` — канонические колонки и `detect_target`
- `src/data/make_dataset.py`, `validation.py`, `synthetic.py`
- `src/features/build_features.py` — обязателен для совместимости API и NN
- `src/models/pipeline.py` — sklearn preprocessor для матрицы признаков NN
- `src/models/evaluate.py::compute_metrics` — единый расчёт метрик
- `src/config.py` — расширить путями для ONNX/NN артефактов
- `params.yaml` (секции `prepare`, существующий `train`) — расширить, не ломая split
- тесты `tests/test_data.py`, `tests/test_features.py` — как база
- `.flake8`, стиль black, Python 3.11

**Переиспользовать с существенной доработкой:**

- `src/api/app.py` — добавить Prometheus, structured logging, A/B, ONNX backend
- `Dockerfile` / `docker-compose.yml` — multi-stage, frontend, observability stack
- `.github/workflows/ci.yml` → multi-stage CI/CD с безопасным skip deploy
- `src/monitoring/drift.py` — оставить PSI как доп. сигнал; основной drift → Evidently
- `dvc.yaml` — добавить стадии train_nn / export_onnx / benchmark

**Не переносить как production path:**

- sole `models/credit_default_model.pkl` как единственный инференс-бэкенд (сохранить как baseline artifact / A-вариант)
- single-stage Docker без resource limits
- CI без security/deploy gates

### 1.4. Совместимость существующего пайплайна с новой нейросетью

**Вывод: совместима при разделении preprocessing и NN-головы.**

Рекомендуемый контракт:

```text
Raw client features (23 cols)
  -> FeatureEngineer (row-wise, без fit)
  -> sklearn ColumnTransformer (fit только на train)
  -> dense float32 matrix X_proc  [n_features ≈ 30–45 after OHE]
  -> PyTorch MLP -> sigmoid P(default=1)
```

Обоснование:

1. **Одинаковый split:** `test_size=0.2`, `random_state=42`, стратификация — из `params.yaml` / `make_dataset`.
2. **Одинаковые сырые признаки:** `RAW_FEATURE_COLUMNS` из `schema.py`.
3. **Одинаковый FE:** `add_features` / `FeatureEngineer` без изменений.
4. **Препроцессинг:** тот же `ColumnTransformer` (median + StandardScaler + OneHotEncoder), fitted на train; сохраняется отдельно (`preprocessor.joblib`), чтобы ONNX содержал только тензорную голову.
5. **Test не участвует в подборе гиперпараметров NN** — только финальная оценка и сравнение с baseline.
6. **API контракт** `ClientFeatures` остаётся; меняется backend инференса (sklearn RF / ONNX NN / A/B).

Риски совместимости:

- число one-hot колонок зависит от категорий, увиденных на train → фиксировать `preprocessor` артефактом;
- дисбаланс 22% → для NN использовать `pos_weight` / weighted BCE, не `class_weight` sklearn;
- ONNX экспорт только `nn.Module`, не всего sklearn Pipeline.

---

## 2. Архитектурные решения

### 2.1. Высокоуровневая архитектура целевой системы

```text
[Data prepare] --CSV/scripts--> train/test
        |
        +--> sklearn RF baseline metrics (immutable JSON)
        |
        +--> preprocessor + MLP train -----> models/preprocessor.joblib
                                           models/credit_scoring_nn.pt|.onnx
        |
        v
[FastAPI ONNX]  <--- ConfigMap/Secret
   /predict (+ optional A/B, AB off by default)
   /metrics  (Prometheus; credit_scoring_* + ml_*)
   structured JSON logs --> Loki (local obs stack)
        |
        v
[Service] --> Deployment (rolling) on kind / Kustomize
        |
[Observability] Prometheus + Grafana + Loki + Alloy + Alertmanager
[Drift] Evidently + quality signals + offline A/B
[Retrain] src/retraining + Airflow DAG (candidate only; NO auto-promote)
[IaC] Terraform (Yandex Cloud) — validate only; apply not executed
[CI/CD] GitHub Actions: build→test→scans→(optional dry-run deploy)
```

**Факт после реализации:** frontend, Ingress и DVC demo-pipeline реализованы и локально проверены
(см. `docs/stage3_completion_report.md`). NetworkPolicy enforcement на kindnet — PARTIAL.

### 2.2. Выбор облачного провайдера

**Выбор: Yandex Cloud.**

Причины:

- явный пункт учебного задания (Yandex / VK / Selectel / Beget);
- Managed Kubernetes + Object Storage + VPC из коробки;
- Terraform-провайдер `yandex-cloud/yandex` зрелый;
- GPU node groups документированы (для отдельного сценария benchmark/infra).

До появления реального аккаунта: только `terraform fmt/validate`, `tflint` (если доступен), документация.
`terraform apply` — **только после явного подтверждения пользователя**.

### 2.3. Модель данных и артефакты

| Артефакт | Назначение |
| --- | --- |
| `data/raw/UCI_Credit_Card.csv` | исходные данные (не в Git) |
| `data/processed/train.csv`, `test.csv` | фиксированный split |
| `models/baseline_rf.pkl` | sklearn baseline (исторические метрики) |
| `models/preprocessor.joblib` | fitted ColumnTransformer |
| `models/credit_scoring_nn.pt` | PyTorch checkpoint + metadata |
| `models/credit_scoring_nn.onnx` | FP32 ONNX |
| `models/credit_scoring_nn.quant.onnx` | dynamic INT8 (CPU) |
| `artifacts/baseline_metrics.json` | зафиксированные RF метрики |
| `artifacts/nn_metrics.json` | реальные NN метрики после обучения |
| `artifacts/onnx_parity.json` | сравнение PyTorch vs ORT |
| `artifacts/benchmark_cpu.json` | latency/throughput/memory |
| `docs/model_benchmark.md` | честный отчёт этапа 1 |

### 2.4. Инференс-стратегия

1. **Staging/prod default (этап 3+):** ONNX Runtime CPU (quantized, если parity OK).
2. **A/B (этап 6):** router по заголовку/проценту: `baseline_rf` vs `onnx_nn`.
3. **GPU path:** отдельный Dockerfile/nodeSelector; локально не обязателен.

### 2.5. Принципы честности

- не выдумывать метрики, benchmarks, успех cloud deploy;
- static `terraform validate` ≠ работающий кластер;
- отсутствие credentials → CI job `deploy` = `skipped`, не green fake;
- concept drift не объявлять без подтверждающих данных/меток.

---

## 3. Структура каталогов

### 3.1. Целевая структура (план этапа 0, исторический)

Ниже — исходный целевой каркас этапа 0 (часть пунктов позже уточнена фактом реализации).

```text
credit-scoring-mlops-deployment/
├── README.md
├── params.yaml
├── requirements*.txt
├── pyproject.toml
├── .github/workflows/               # ci-python/docker/infra/k8s + cd + airflow
├── docker/                          # Dockerfile.api, Dockerfile.models, Dockerfile.airflow
├── docker-compose.yml
├── docker-compose.observability.yml
├── docker-compose.airflow.yml
├── src/{data,features,models,nn,api,monitoring,retraining}/
├── tests/
├── k8s/{base,overlays/local,kind}/
├── infra/terraform/{modules,environments}/
├── monitoring/{prometheus,grafana,loki,alloy,...}/
├── airflow_home/dags/               # не `airflow/` — чтобы не shadow'ить пакет airflow
├── configs/{monitoring,retraining}/
├── scripts/
├── docs/
├── data/{raw,processed}/
├── models/
└── artifacts/
```

### 3.2. Факт после этапов 1–7

- Каркас + код этапов **1–7 реализованы** (см. README и matrix).
- DVC demo-pipeline + local remote: `verified_local` (не UCI raw; не production ONNX outs).
- Frontend / Ingress: `verified_local` (host kind `:8080` может требовать recreate).
- DAG: `airflow_home/dags/credit_scoring_retraining.py`.
- Compose-профили разделены: API, observability, airflow (не поднимать всё сразу на 8 GB).

---

## 4. Зависимости

### 4.1. Уже есть в исходнике (перенос)

`pandas`, `numpy`, `scikit-learn`, `matplotlib`, `PyYAML`, `pandera`, `mlflow<3`, `dvc`, `fastapi`, `uvicorn`, `pydantic`, `joblib`, `pytest`, `httpx`, `flake8`, `black`

### 4.2. Новые (по этапам)

| Пакет / инструмент | Этап | Назначение | Замечание по RAM |
| --- | --- | --- | --- |
| `torch` (CPU wheel) | 1 | обучение MLP | ставить CPU-only; ~1–2 GB disk |
| `onnx`, `onnxruntime` | 1 | export + inference | без GPU ORT |
| `psutil` | 1 | RSS memory в benchmarks | лёгкий |
| Terraform + yandex provider | 2 | IaC | без apply |
| `prometheus-fastapi-instrumentator` или `prometheus_client` | 5 | метрики | |
| `python-json-logger` / stdlib JSON | 5 | structured logs | |
| `evidently` | 6 | data drift | тяжёлая зависимость; изолировать |
| `apache-airflow` | 7 | DAG | **не ставить в основной venv на 8 GB**; отдельный compose-сервис |
| `trivy` / `hadolint` (CI) | 4 | security scan | в GitHub Actions |
| `kubeconform` / `kubeval` | 4 | validate manifests | |

Рекомендация по окружениям на Windows:

1. `.venv` — core + API + sklearn + (опционально) torch CPU.
2. Docker Compose — Airflow, Prometheus, Grafana, Loki.
3. Не ставить полный Airflow + torch + Evidently одновременно в один host venv.

---

## 5. Оценка потребления локальных ресурсов

| Сценарий | CPU | RAM (оценка) | Диск | Допустимость на 8 GB |
| --- | --- | --- | --- | --- |
| Подготовка данных + pytest | низкая | <1 GB | малый | Да |
| Обучение sklearn baseline | средняя | 1–2 GB | mlruns | Да (`n_jobs=1`) |
| Обучение маленькой MLP (CPU) | средняя | 1.5–3 GB | checkpoints | Да при batch≤256, 2–3 слоя |
| ONNX benchmark (batch 1–64) | средняя | <1 GB runtime | малый | Да |
| Docker Compose: api+frontend | средняя | 0.5–1 GB | images | Да |
| Compose + Prometheus/Grafana/Loki | высокая | 2.5–4.5 GB | images | Да осторожно; лимиты контейнеров |
| Compose + Airflow (+DB) | высокая | +1.5–3 GB | images | Рискованно; запускать отдельно |
| Managed K8s / GPU | облако | — | — | Только после подтверждения |
| Полный стек одновременно | очень высокая | >8 GB | — | **Нет** — профили compose |

Правила локальной работы:

- Torch CPU-only, `OMP_NUM_THREADS`/`torch.set_num_threads(2–4)`.
- В Docker — `mem_limit` / K8s requests-limits.
- Airflow и observability не держать up 24/7 на учебном ПК.
- GPU benchmarks — skip, если `torch.cuda.is_available() == False`.

---

## 6. Риски

| ID | Риск | Влияние | Митигация |
| --- | --- | --- | --- |
| R1 | OOM при одновременном Docker-стеке | Блок локальной проверки | Профили compose: `api`, `obs`, `airflow` |
| R2 | Тяжёлый `torch` в CI | Долгий/падающий pipeline | Кеш pip; CPU wheel; отдельные optional jobs |
| R3 | Нет DVC remote / нет CSV в Git | Невоспроизводимость после clone | Документировать ручную укладку CSV; позже Object Storage remote |
| R4 | NN хуже RF по ROC-AUC | «Плохие» цифры в отчёте | Честно зафиксировать; baseline не подменять; продвижение gated |
| R5 | ONNX parity fail после quantization | Неверный инференс | Порог max abs/MAE; quantized не в prod без прохождения |
| R6 | Платный Yandex Cloud | Неожиданные расходы | Только validate до подтверждения; budget alerts в docs |
| R7 | Secrets в Git | Провал security | templates + `.env.example`; tfvars в gitignore |
| R8 | Fake-green deploy без credentials | Ложная готовность | explicit `if: secrets...`; job conclusion skipped |
| R9 | Concept drift без меток | Неверные выводы | Разделить data drift / performance decay / concept hypothesis |
| R10 | Кириллические пути Windows | Ломаются некоторые CLI | Работать из короткого path / WSL2 для K8s tooling при необходимости |

---

## 7. План по этапам (обзор) → факт выполнения

Учебная нумерация совпадает с README: **0 → 1 → 2 (Terraform) → 3 (Docker/K8s) → 4 → 5 → 6 → 7**.

| Этап | Содержание | Статус кода | Проверка |
| --- | --- | --- | --- |
| 0 | Аудит + план + матрица | Готово | `verified_local` |
| 1 | PyTorch NN, ONNX, quant, CPU bench | Готово | `verified_local` (GPU: skip) |
| 2 | Terraform modules (YC) | Готово | fmt/validate local+CI; **apply `not_executed`** |
| 3 | Docker, kind/Kustomize, frontend, Ingress, DVC | Готово локально | `verified_local`; NP enforcement `partial` |
| 4 | GitHub Actions | Готово | **verified_ci** на `65de3ad` (5 workflows); prod deploy `not_executed` |
| 5 | Observability stack | Готово локально | `verified_local`; cloud obs `not_executed` |
| 6 | Evidently, quality signals, A/B | Готово | `verified_local`; **no auto-promote** |
| 7 | Airflow retraining (gated) | Engine+DAG+compose+E2E | Docker A/A2/B/C/D/E + scheduler cron proof `verified_local`; CI parse `verified_ci`; **no auto-promote** |
| Docs | README, runbooks, matrix | Готово | `verified_local` |

**Правило честности (сохранено):** static validate ≠ cloud success; skip без credentials ≠ fake green; concept drift не объявлять без оснований.

---

## 8. Детальный план этапа 1 (исторический; выполнен)

> Ниже — исходный план запуска этапа 1. Критерии закрыты; отчёты:
> [`docs/stage1_audit_report.md`](stage1_audit_report.md), [`docs/model_benchmark.md`](model_benchmark.md),
> [`docs/stage1_model_optimization_completion_report.md`](stage1_model_optimization_completion_report.md) (Block 7),
> [`docs/production_resource_sizing.md`](production_resource_sizing.md).
> Baseline RF test ROC-AUC **0.7771**; MLP/ONNX FP32 **0.7742**.
> Block 7: CPU/API local VERIFIED; hardened Colab GPU `VERIFIED_GPU` (`results/block7/colab/hardened/`); historical Colab kept separate; production artifacts unchanged.

### 8.1. Цели (план)

1. Перенести/адаптировать data+FE+preprocessor из исходника.
2. Реализовать воспроизводимую MLP для бинарной классификации.
3. Сохранить checkpoint, params, метрики эксперимента.
4. Экспортировать в ONNX; проверить parity с PyTorch.
5. Dynamic quantization (ORT); сравнить size / ROC-AUC / F1 / latency / throughput / RSS.
6. CPU benchmarks для нескольких batch sizes.
7. GPU scenario как отдельный скрипт с auto-skip.
8. Честный benchmark-отчёт только с измеренными числами.
9. Pytest на NN forward, export, parity threshold.
### 8.2. Предлагаемая архитектура NN

- Вход: размерность после preprocessor (`n_in`).
- Скрытые слои: `Linear → BatchNorm1d → ReLU → Dropout` × 2
  размеры по умолчанию: `[128, 64]` (можно `[64, 32]` при нехватке RAM).
- Выход: `Linear(n_in_last, 1)` + sigmoid при inference (BCEWithLogitsLoss на train).
- Оптимизатор: Adam; early stopping по val ROC-AUC (val = stratified split **внутри train**, не test).
- Seeds: `random`, `numpy`, `torch`; `deterministic` где возможно на CPU.

### 8.3. Последовательность работ этапа 1

1. Bootstrap репозитория: скопировать переиспользуемые модули, `params.yaml`, тесты данных.
2. Зафиксировать `artifacts/baseline_metrics.json` с историческими RF метриками (без пересчёта «улучшений»).
3. Реализовать `src/nn/model.py`, `train_nn.py`, `export_onnx.py`, `quantize.py`, `benchmark.py`, `parity.py`.
4. Расширить `params.yaml` секцией `nn` / `onnx` / `benchmark`.
5. Добавить DVC-стадии (или scripts) для nn train/export/bench.
6. Написать тесты на синтетике (без обязательного полного UCI в CI).
7. При наличии `data/raw/UCI_Credit_Card.csv` — полный прогон и заполнение benchmark-отчёта.
8. Технический отчёт этапа 1: что измерено / что skip.

### 8.4. Критерии готовности этапа 1

- [x] NN обучается воспроизводимо на том же split.
- [x] Test не использован для подбора гиперпараметров.
- [x] ONNX parity в пределах порога.
- [x] Есть FP32 и quantized артефакты + сравнение размеров.
- [x] CPU benchmark JSON + markdown отчёт без выдуманных цифр.
- [x] GPU bench явно skipped без GPU.
- [x] Pytest по NN/ONNX на синтетике/доступных данных.
- [x] Baseline RF метрики не переписаны.

### 8.5. Команды проверки (исторический план этапа 1)

```powershell
# from repository root
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt -r requirements-nn.txt

# данные: положить UCI_Credit_Card.csv в data/raw/
python -m src.data.make_dataset
python -m src.nn.train_nn
python -m src.nn.export_onnx
python -m src.nn.parity
python -m src.nn.quantize
python -m src.nn.benchmark --device cpu
python -m src.nn.benchmark --device cuda   # ожидаемый skip без GPU

pytest -v
flake8 src tests
black --check src tests
```

---

## 9. Что реально проверено на этапе 0 (история)

| Проверка | Результат на этапе 0 |
| --- | --- |
| Скачивание исходного репозитория (ZIP) | Успешно |
| `git clone` исходника | Неуспешно (`fatal: '$GIT_DIR' too big`) — использован ZIP |
| Чтение README, params, dvc, train, pipeline, FE, schema, API, CI, Dockerfile, drift | Выполнено |
| Наличие локального UCI CSV в новом проекте | Не проверялось / не копировалось |
| Обучение моделей / benchmarks | **На этапе 0 не выполнялось** (выполнено позже, этап 1) |
| Docker / Terraform / K8s | **На этапе 0 не выполнялось** (выполнено позже) |
| Создание облачных ресурсов | **Не выполнялось** (и к сдаче тоже `not_executed`) |

---

## 10. Итог перед сдачей

Этапы **0–7 реализованы** в репозитории. Актуальная точка входа — [`README.md`](../README.md) и [`docs/requirements_matrix.md`](requirements_matrix.md).

Остаются намеренные ограничения:

1. **Нет** cloud `terraform apply` и **нет** production в Yandex Cloud.
2. Airflow Docker E2E — **`verified_local`** only (см. `stage7_airflow_e2e_report.md`).
3. **Нет** auto-promote candidate/challenger в production.
4. DVC demo-pipeline подтверждён локально; cloud remote — по желанию позже.
5. Frontend / Ingress подтверждены локально; NP deny/allow на kindnet не enforce.

Дальнейшие действия (вне обязательного DoD сдачи): ручной promotion модели после review; опциональный Airflow compose при свободной RAM; cloud apply только после явного подтверждения.
