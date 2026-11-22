# Stage 1 — Final Technical Audit

**Дата:** 2026-11-22  
**Объём:** только этап 1 (без смены архитектуры, без этапа 2, без commit/push/cloud)  
**Проверки качества после правок:** `pytest` 35 passed; `flake8` 0; `black --check` 0

Легенда: **PASS** / **FAIL** / **WARNING**

---

## Сводка

| # | Пункт | Вердикт |
| --- | --- | --- |
| 1 | Data leakage | **PASS** |
| 2 | Признаки и порядок колонок train↔ONNX | **PASS** |
| 3 | ONNX parity полный raw→preprocess→infer | **PASS** |
| 4 | Метрики на фиксированном test | **PASS** |
| 5 | Влияние quantization на классификацию | **PASS** (после доработки) |
| 6 | Методология CPU benchmark | **PASS** (после доработки) |
| 7 | Python 3.13 и зависимости | **WARNING** |
| 8 | Git hygiene (данные/веса/секреты) | **PASS** (с замечанием) |
| 9 | Документация ↔ матрица этапа 1 | **PASS** |

Исправления в рамках аудита (без смены архитектуры):

- `src/nn/quantize.py` — decision flip rate / max&mean Δp
- `src/nn/benchmark.py` — раздельные scopes `model_only` и `end_to_end`
- `src/nn/parity.py` — явный raw path + feature contract
- `src/models/preprocessing.py` — контракт порядка колонок
- `src/nn/train_nn.py` — убран неиспользуемый `best_state`; сохранение feature contract
- `.gitignore` — разрешён трекинг `artifacts/baseline_metrics.json`
- `tests/test_preprocessing.py` — тест порядка колонок

---

## 1. Data leakage — PASS

**Файлы:** `src/data/make_dataset.py`, `src/nn/train_nn.py`, `params.yaml`

Подтверждено:

- Split до модели: `test_size=0.2`, `random_state=42`, stratify по target → **24000 / 6000**.
- Внутренний val = 20% от **train only** (`nn.val_size`), stratify.
- Early stopping / выбор `best_epoch` — по **val ROC-AUC**, не по test.
- Preprocessor stage-1 (для early stopping) fit на `x_fit_raw` (train без val).
- Production preprocessor fit на **полном train**, без test.
- Test используется только для финального `compute_metrics`.
- Hyperparameters зафиксированы в `params.yaml`, на test не подбирались.
- Независимый пересчёт test-метрик совпал с `artifacts/nn_metrics.json` (`match True`).

**Не leakage:** включение val-части train в финальный preprocessor/retrain — стандартная практика после выбора эпохи.

---

## 2. Признаки и порядок колонок — PASS

**Файлы:** `src/schema.py`, `src/features/build_features.py`, `src/models/pipeline.py`, `src/models/preprocessing.py`, `artifacts/feature_contract.json`

Подтверждено:

- Raw serving-контракт: фиксированный `RAW_FEATURE_COLUMNS` (23).
- После FE: `MODEL_FEATURE_COLUMNS` в фиксированном порядке.
- `ColumnTransformer`: сначала `NUMERIC_FEATURES`, затем `CATEGORICAL_FEATURES`.
- ONNX input dim = **47** = `feature_contract.input_dim`.
- Тест `test_feature_contract_preserves_column_order`: перестановка raw-колонок не меняет матрицу (canonical select внутри FE).
- В `artifacts/onnx_parity.json` сохранены `raw_feature_columns` и `feature_contract`.

---

## 3. ONNX parity полный путь — PASS

**Файлы:** `src/nn/parity.py`, `artifacts/onnx_parity.json`

Подтверждено:

- Старт с raw test CSV → drop target → reorder `RAW_FEATURE_COLUMNS` → `preprocessor.joblib` → PyTorch/ONNX → sigmoid.
- `verifies_full_raw_path: true`.
- Batch 1/16/64/256 и full test (6000): max\|Δp\| ≤ 7.1e-08, **passed=true**.

Это не «только нейросеть на заранее готовом тензоре без preprocessor»: preprocessor применяется в том же скрипте к raw input.

---

## 4. Метрики на фиксированном test — PASS

**Файлы:** `src/models/evaluate.py::compute_metrics`, `artifacts/nn_metrics.json`

| Метрика | Формула | Результат test |
| --- | --- | ---: |
| ROC-AUC | `roc_auc_score(y, p)` | 0.774154 |
| PR-AUC | `average_precision_score(y, p)` | 0.550928 |
| Precision/Recall/F1/Accuracy | threshold=0.5 на `p` | 0.4375 / 0.6307 / 0.5167 / 0.7390 |

Независимый пересчёт sklearn на том же checkpoint/preprocessor: **байт-в-байт совпадение** с сохранённым отчётом.

RF baseline не изменялся (`artifacts/baseline_metrics.json`).

---

## 5. Влияние quantization — PASS (после доработки)

**Файлы:** `src/nn/quantize.py`, `artifacts/onnx_quantization.json`

До аудита не хватало доли смены решений — **добавлено**.

Измерения на test (n=6000, threshold=0.5):

| Показатель | Значение |
| --- | ---: |
| Decision flip rate | **2.1833%** (131/6000) |
| Flips 0→1 | 48 |
| Flips 1→0 | 83 |
| Mean \|Δp\| | 0.01605 |
| Max \|Δp\| | 0.11676 |
| RMSE Δp | 0.02191 |
| Size | 62934 → 24223 bytes |
| ROC-AUC fp32 / quant | 0.7742 / 0.7720 |

Вывод аудита: quantized **не** эквивалентен FP32 по решениям; для serving default остаётся ONNX FP32.

---

## 6. CPU benchmark methodology — PASS (после доработки)

**Файлы:** `src/nn/benchmark.py`, `artifacts/benchmark_cpu.json`

До аудита был только model-only — **добавлен end-to-end**.

Методика:

- warmup=20, timed=100, repeats=3
- p50/p95 по замерам, усреднение по repeats
- одинаковые batch sizes `{1,16,64,256}` и одни и те же test-строки
- scopes:
  - `model_only` — forward по готовой float32-матрице
  - `end_to_end` — raw DataFrame → preprocessor → model
- GPU: `SKIPPED` (`artifacts/benchmark_gpu.json`)

Факт: end-to-end (~9–12 ms @ bs=1) Dominируется preprocessor/pandas; model-only ONNX FP32 ~0.016 ms.

---

## 7. Python 3.13 и зависимости — WARNING

**Файлы:** `requirements*.txt`, runtime

| Компонент | Факт |
| --- | --- |
| Python | **3.13.7** (не 3.11 из ТЗ) |
| torch | 2.15.0+cpu |
| onnx | 1.23.2 |
| onnxruntime | 1.32.0 |
| scikit-learn | 1.9.1 |

Прогон обучения/ONNX/quant/bench/pytest на 3.13 успешен.  
**WARNING:** в requirements используются нижние границы (`>=`), без freeze lockfile; воспроизводимость версий не абсолютная. Python 3.11 на машине отсутствует (пустая папка Doc).

---

## 8. Git hygiene — PASS (с замечанием)

**Файлы:** `.gitignore`

Игнорируются (проверено `git check-ignore`):

- `data/raw/*.csv` (датасет)
- `models/*` (веса/ONNX/preprocessor)
- `artifacts/*` кроме `.gitkeep` и **`baseline_metrics.json`**
- `.venv/`, `.env`, ключи, tfstate

Замечание: `artifacts/baseline_metrics.json` теперь **разрешён** к трекингу negation-правилом, но в индекс ещё не добавлен (commit не выполнялся по требованию). Сгенерированные `nn_metrics.json`, ONNX, checkpoint в Git не попадают.

Секреты в репозитории не обнаружены.

---

## 9. Документация и матрица этапа 1 — PASS

**Файлы:** `docs/model_benchmark.md`, `docs/requirements_matrix.md` (IDs 1.1–1.13), `README.md`

- Матрица этапа 1 отмечена `verified_local`.
- Benchmark-отчёт содержит архитектуру, параметры, RF comparison, parity, quant, CPU, GPU skip, ограничения, рекомендацию serving.
- После аудита добавлены decision flips и dual-scope latency (см. обновление `docs/model_benchmark.md`).

---

## Повторные проверки качества

```text
pytest  -> 35 passed
flake8  -> exit 0
black --check -> exit 0
```

---

## Остаточные WARNING (не блокируют этап 1)

1. Python 3.13 вместо 3.11.  
2. Unpinned dependency ranges.  
3. End-to-end latency на CPU почти одинакова для backends из-за preprocessor overhead.  
4. `baseline_metrics.json` ещё не в git index (готов к add, commit не делался).

**Итог аудита:** этап 1 технически принят после точечных исправлений. К этапу 2 не переходим.
