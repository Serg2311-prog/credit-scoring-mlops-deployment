# Stage 1 — Model & ONNX Benchmark Report

**Дата исходного прогона:** 2026-11-22
**Block 7 refresh:** 2026-11-24 (`artifacts/block7/`, см. [`stage1_model_optimization_completion_report.md`](stage1_model_optimization_completion_report.md))
**Среда:** Windows 11, Python 3.13.7 (CPU torch 2.15.0+cpu), Intel Core i5-1135G7, ~8 GB RAM, GPU отсутствует
**Данные:** UCI Default of Credit Card Clients, train=24000 / test=6000, `test_size=0.2`, `random_state=42`

Все числа ниже взяты из локальных артефактов. Выдуманных метрик нет. Production ONNX/preprocessor/registry/`dvc.lock` в Block 7 **не** перезаписывались.

Исходные JSON (Stage 1) + Block 7:

- `artifacts/baseline_metrics.json`
- `artifacts/nn_metrics.json`
- `artifacts/onnx_parity.json`
- `artifacts/onnx_quantization.json`
- `artifacts/benchmark_cpu.json`
- `artifacts/benchmark_gpu.json`
- `artifacts/block7/*` (local working copies; gitignored)
- **`results/block7/*`** — compact Git-tracked evidence for clone/review

---

## 1. Архитектура MLP

| Параметр | Значение |
| --- | --- |
| Класс | `CreditScoringMLP` |
| Вход | 47 признаков после `FeatureEngineer` + sklearn `ColumnTransformer` |
| Скрытые слои | `[128, 64]` |
| Блок слоя | `Linear → BatchNorm1d → ReLU → Dropout(0.2)` |
| Выход | 1 logit (`BCEWithLogitsLoss`) |
| Loss imbalance | `pos_weight = n_neg / n_pos` |
| Оптимизатор | Adam, `lr=0.001`, `weight_decay=1e-4` |
| Batch size | 256 |
| Max epochs | 40 |
| Early stopping | patience=7 по **val ROC-AUC** (val = 20% от train) |
| Threads | `torch.set_num_threads(2)` |
| Seed | 42 |

Пайплайн признаков:

```text
raw client fields
  -> FeatureEngineer (row-wise)
  -> SimpleImputer + StandardScaler / OneHotEncoder  (fit only on train)
  -> float32 matrix [N, 47]
  -> MLP logits -> sigmoid probability
```

Test **не** использовался для подбора гиперпараметров и early stopping.

---

## 2. Параметры обучения (факт прогона)

| Показатель | Значение |
| --- | ---: |
| Best epoch by val | 10 |
| Best val ROC-AUC | 0.7740 |
| Retrain epochs on full train | 10 |
| Early stop triggered | epoch 17 |

---

## 3. Сравнение с исходным Random Forest baseline

RF baseline — **исторические** метрики исходного проекта `credit-default-prediction`. Они не пересчитывались и не «улучшались».

| Метрика (test) | RF baseline | MLP (этот прогон) | Δ |
| --- | ---: | ---: | ---: |
| ROC-AUC | **0.7771** | 0.7742 | −0.0029 |
| PR-AUC | **0.5536** | 0.5509 | −0.0027 |
| Precision | **0.4786** | 0.4375 | −0.0411 |
| Recall | 0.6081 | **0.6307** | +0.0226 |
| F1 | **0.5357** | 0.5167 | −0.0190 |
| Accuracy | **0.7668** | 0.7390 | −0.0278 |

**Вывод:** MLP **уступает** RF baseline по ROC-AUC / PR-AUC / F1 / Accuracy на test. Это зафиксировано честно. Для промышленного скоринга по качеству пока предпочтителен RF; ONNX MLP имеет смысл как оптимизируемый инференс-кандидат и объект A/B на следующих этапах.

---

## 4. ONNX parity (PyTorch vs ORT FP32)

Файл: `models/credit_scoring_nn.onnx` (opset 17, dynamic batch).

| Проверка | max\|Δp\| | MAE | Статус |
| --- | ---: | ---: | --- |
| batch=1 | 0 | 0 | passed |
| batch=16 | 2.65e-08 | 9.11e-09 | passed |
| batch=64 | 6.41e-08 | 9.65e-09 | passed |
| batch=256 | 6.41e-08 | 9.10e-09 | passed |
| full test (6000) | 7.08e-08 | 1.05e-08 | passed |

Пороги: `parity_atol=1e-5`, `parity_mae_atol=1e-6`.
Полный путь `raw → preprocessor.joblib → model → sigmoid` согласован.

---

## 5. Dynamic quantization

Метод: `onnxruntime.quantization.quantize_dynamic`, `weight_type=QInt8`.

Из-за кириллических путей Windows quantization выполнялась через ASCII temp directory (см. `src/nn/quantize.py`).

| Показатель | ONNX FP32 | ONNX Quantized |
| --- | ---: | ---: |
| Size, bytes | 62934 | **24223** (~0.385×) |
| ROC-AUC | **0.7742** | 0.7720 |
| Precision | 0.4375 | 0.4446 |
| Recall | **0.6307** | 0.6292 |
| F1 | 0.5167 | **0.5211** |
| Accuracy | 0.7390 | **0.7442** |
| Prob MAE vs FP32 | — | 0.0160 |
| Prob max\|Δ\| vs FP32 | — | 0.1168 |
| Decision flips @0.5 | — | **131 / 6000 (2.183%)** |
| Flips 0→1 / 1→0 | — | 48 / 83 |

Quantized модель **меньше по размеру**, но вероятность заметно отклоняется от FP32; ROC-AUC чуть ниже; **2.18% решений меняются**. Она **не объявляется лучшей** автоматически.

---

## 6. CPU benchmarks

Методика (`artifacts/benchmark_cpu.json`):

- одинаковые raw/test строки и batch sizes для всех backend;
- warmup=20, timed=100, repeats=3;
- p50/p95 по замерам, усреднение по repeats;
- **два scope отдельно**:
  - `model_only` — forward по готовой float32-матрице;
  - `end_to_end` — raw DataFrame → `preprocessor.joblib` → model;
- throughput ≈ `batch_size / mean_latency_s`;
- memory = RSS процесса (включает загруженный PyTorch) — поэтому абсолютный RSS высокий и почти одинаковый.

### 6.1. Качество на test (из benchmark прогона)

| Backend | ROC-AUC | Precision | Recall | F1 | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| PyTorch CPU | 0.7742 | 0.4375 | 0.6307 | 0.5167 | 0.7390 |
| ONNX FP32 CPU | 0.7742 | 0.4375 | 0.6307 | 0.5167 | 0.7390 |
| ONNX Quant CPU | 0.7736 | 0.4427 | 0.6292 | 0.5198 | 0.7428 |

### 6.2. Latency / throughput (model_only)

| Backend | Batch | p50 ms | p95 ms | Throughput samples/s |
| --- | ---: | ---: | ---: | ---: |
| PyTorch CPU | 1 | 0.136 | 0.159 | 6.9e3 |
| PyTorch CPU | 16 | 0.127 | 0.143 | 1.22e5 |
| PyTorch CPU | 64 | 0.164 | 0.246 | 3.77e5 |
| PyTorch CPU | 256 | 0.203 | 0.256 | 1.19e6 |
| ONNX FP32 | 1 | **0.016** | 0.017 | 6.05e4 |
| ONNX FP32 | 16 | 0.028 | 0.031 | 5.74e5 |
| ONNX FP32 | 64 | 0.062 | 0.066 | 1.09e6 |
| ONNX FP32 | 256 | 0.152 | 0.193 | 1.69e6 |
| ONNX Quant | 1 | 0.031 | 0.033 | 3.20e4 |
| ONNX Quant | 16 | 0.031 | 0.037 | 5.01e5 |
| ONNX Quant | 64 | 0.070 | 0.077 | 8.92e5 |
| ONNX Quant | 256 | 0.161 | 0.174 | 1.63e6 |

### 6.3. Latency end-to-end (raw → preprocess → model)

| Backend | Batch | p50 ms | p95 ms | Throughput samples/s |
| --- | ---: | ---: | ---: | ---: |
| PyTorch CPU | 1 | 11.35 | 15.69 | 81 |
| ONNX FP32 | 1 | 9.11 | 10.40 | 108 |
| ONNX Quant | 1 | 9.21 | 10.30 | 107 |
| ONNX FP32 | 256 | 11.50 | 12.49 | 2.27e4 |
| ONNX Quant | 256 | 11.29 | 12.92 | 2.27e4 |

End-to-end почти одинаков для backends: доминирует preprocessor/pandas, не сам forward.

### 6.4. Размеры артефактов

| Артефакт | Size, bytes |
| --- | ---: |
| `credit_scoring_nn.pt` | 67315 |
| `credit_scoring_nn.onnx` | 62934 |
| `credit_scoring_nn.quant.onnx` | **24223** |

---

## 7. GPU benchmark

Исторический артефакт мог содержать `SKIPPED`. Block 7 фиксирует явный статус:

```json
{"device": "cuda", "status": "BLOCKED_NO_GPU", "torch_cuda_is_available": false}
```

Команда: `python -m src.nn.benchmark --device cuda` — **без** silent CPU fallback и **без** выдуманных GPU latency.
Инструкция внешнего прогона: [`gpu_benchmark_colab.md`](gpu_benchmark_colab.md). Статус **не** `VERIFIED_GPU`.

---

## 8. Block 7 refresh (2026-11-24)

### 8.1. Parity re-check

| n | max\|Δp\| | MAE | class agreement | Tolerances | Result |
| ---: | ---: | ---: | ---: | --- | --- |
| 6000 | 7.08e-08 | 1.05e-08 | 1.0 | atol 1e-5 / mae 1e-6 | **PASS** |

### 8.2. CPU model_only (batches 1/8/32/64/128)

ORT FP32 batch=1 p50 ≈ **0.021 ms** vs PyTorch ≈ 0.141 ms. Quantized часто **не быстрее** FP32 на этом CPU. Полная таблица: `artifacts/block7/cpu_benchmark_summary.csv`.

### 8.3. API load (local uvicorn, synthetic)

Peak ≈ **55 RPS** at concurrency=1; p95 grows with concurrency; health OK after test. Details: `artifacts/block7/api_load_results.json`.

### 8.4. Production sizing

[`production_resource_sizing.md`](production_resource_sizing.md) — keep existing K8s CPU/mem/replicas and ORT threads=2; FP32 default; GPU not required.

How to reproduce:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe scripts\block7_eval.py
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe scripts\api_load_test.py --concurrency 1,2,4,8 --duration 8 --min-free-mb 350
```

---

## 9. Ограничения эксперимента

1. Локально установлен Python **3.13**, не 3.11.
2. Нет GPU — GPU numbers отсутствуют (`BLOCKED_NO_GPU`).
3. MLP не превзошла RF baseline по ключевым метрикам качества.
4. Dynamic quantization даёт сжатие, но ухудшает parity вероятностей (max abs ~0.12).
5. На batch=1 quantized ONNX **медленнее** FP32 ONNX в прогонах; ускорение **не** утверждается без измерений.
6. RSS включает весь процесс с импортированным torch — это не изолированный memory footprint модели.
7. `model_only` не включает preprocessor; `end_to_end` и API load — включают.
8. ORT quantization на путях с кириллицей требует temp ASCII workaround.
9. API load — локальный uvicorn, не cloud SKU.

---

## 10. Рекомендация для дальнейшего развертывания

| Цель | Рекомендация |
| --- | --- |
| Максимальное качество (offline/baseline) | Исторический **RandomForest** (`artifacts/baseline_metrics.json`) |
| Быстрый CPU inference с паритетом к обученной NN | **ONNX FP32** (`models/credit_scoring_nn.onnx`) |
| Минимальный размер артефакта | ONNX Quantized — только после продуктового решения о допуске Δp / flips |
| API / K8s resources | См. [`production_resource_sizing.md`](production_resource_sizing.md) — текущие overlays **оставить** |
| GPU | Не нужен для этой MLP; IaC GPU opt-in остаётся выключенным |

**Итог:** NN→ONNX→quant→CPU/API benchmarks **измерены**. Serving default — **ONNX FP32**. Quantized — опциональный кандидат, не default. GPU — `BLOCKED_NO_GPU`.
