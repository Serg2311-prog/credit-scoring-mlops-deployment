# Block 7 / Stage 1 — Model Optimization & Benchmarking Completion Report

**Date:** 2026-11-24
**Scope:** Stage 1 — NN, ONNX, quantization, CPU/GPU benchmarking, API load, production sizing
**Constraint:** production ONNX / preprocessor / `model_registry.json` / `dvc.lock` **unchanged**; no retrain

Status legend: `IMPLEMENTED` · `VERIFIED_STATIC` · `VERIFIED_LOCAL` · `VERIFIED_HOSTED` · `VERIFIED_GPU` · `NOT_EXECUTED` · `BLOCKED_NO_GPU`

---

## 1. TZ requirements audit

| Requirement | Implementation | Evidence | Gap before Block 7 | Fix in Block 7 |
| --- | --- | --- | --- | --- |
| New neural net (PyTorch MLP) | `CreditScoringMLP` + train pipeline | `src/nn/*`, `artifacts/nn_metrics.json` | None for core train | None (no retrain) |
| Convert to ONNX | Export opset 17 FP32 | `models/credit_scoring_nn.onnx` | — | Unchanged production artifact |
| Conversion validation | Parity script + atol/mae | `artifacts/block7/parity_summary.json` **PASS** | Class agreement not always summarized | `src/nn/parity.py` + Block 7 re-run |
| Compare original vs ONNX on CPU | PyTorch vs ORT FP32 benches | `artifacts/block7/benchmark_cpu_block7.json` | Batch set incomplete vs TZ | Batches **1,8,32,64,128** |
| Quantization or pruning | Dynamic QInt8 ORT | `models/credit_scoring_nn.quant.onnx` + deltas | Need honest latency claim | Deltas + CPU table; **no false speedup** |
| Metrics before/after optimization | Holdout FP32 vs quant | `quantization_deltas.json` | — | Absolute + relative deltas |
| Load testing CPU/GPU | CPU bench + API HTTP load | CPU JSON + `api_load_results.json` | No concurrent API load script | `scripts/api_load_test.py` **VERIFIED_LOCAL** |
| Optimal production resources | Sizing doc vs K8s overlays | `docs/production_resource_sizing.md` | Implicit only | Documented; manifests **kept** |
| Benchmark report | Docs + JSON/CSV/plots | this report + `docs/model_benchmark.md` | GPU status naming | `BLOCKED_NO_GPU` + Colab instructions |
| GPU benchmark | Runner with no silent CPU fallback | `artifacts/block7/benchmark_gpu.json` | Status was SKIPPED | Explicit **BLOCKED_NO_GPU** — **not** VERIFIED_GPU |

---

## 2. Model correctness (PyTorch ↔ ONNX FP32)

| Field | Value |
| --- | --- |
| Holdout size | **6000** (fixed test split) |
| max abs error | **7.08e-08** |
| mean abs error | **1.05e-08** |
| Class agreement @0.5 | **1.0** (6000/6000) |
| Tolerances | `parity_atol=1e-5`, `parity_mae_atol=1e-6` |
| Result | **PASS** |

Data leakage: preprocessor fit on train only; val from train; test unused for HP — prior Stage 1 audit still holds. Feature order contract unchanged.

Production artifacts were **not** rewritten.

---

## 3. Quantization evaluation (fixed holdout, threshold=0.5)

| Metric | FP32 | Quant | Abs Δ | Rel Δ |
| --- | ---: | ---: | ---: | ---: |
| ROC-AUC | 0.77415 | 0.77203 | −0.00212 | −0.274% |
| PR-AUC | 0.55093 | 0.54707 | −0.00385 | −0.700% |
| Precision | 0.43753 | 0.44462 | +0.00709 | +1.62% |
| Recall | 0.63075 | 0.62924 | −0.00151 | −0.239% |
| F1 | 0.51667 | 0.52106 | +0.00439 | +0.850% |
| Accuracy | 0.73900 | 0.74417 | +0.00517 | +0.699% |
| Size (bytes) | 62934 | 24223 | — | **0.385×** |
| Decision flips | — | 131 / 6000 (2.18%) | — | — |

Confusion FP32: tn=3597 fp=1076 fn=490 tp=837 · Quant: tn=3630 fp=1043 fn=492 tp=835.

**Latency claim:** on this CPU, quantized ORT is **often not faster** than FP32 (see CPU table). Size reduction is real; automatic “quantization speeds inference” is **rejected**.

---

## 4. CPU inference benchmark

Environment: see `artifacts/block7/environment.json` / `run_config.json`.
Methodology: warmup=20, timed=100, repeats=3; scopes `model_only` vs `end_to_end`; seeds fixed in pipeline.

### model_only p50 (ms) / throughput (samples/s)

| Variant | b=1 | b=8 | b=32 | b=64 | b=128 |
| --- | ---: | ---: | ---: | ---: | ---: |
| PyTorch FP32 p50 | 0.141 | 0.133 | 0.125 | 0.144 | 0.177 |
| ORT FP32 p50 | **0.021** | 0.028 | 0.044 | 0.066 | 0.098 |
| ORT Quant p50 | 0.027 | 0.026 | 0.047 | 0.070 | 0.109 |
| ORT FP32 tps | 4.8e4 | 2.5e5 | 7.4e5 | 9.7e5 | 1.3e6 |

Full percentiles, cold start, RSS: `benchmark_cpu_block7.json`, CSV `cpu_benchmark_summary.csv`.
Thread probe (batch=32): ORT FP32 strongest at **1–2** threads (`cpu_thread_probe.json`).

end-to-end batch=1 ≈ 10–11 ms for all backends (preprocess-dominated).

Status: **VERIFIED_LOCAL**.

---

## 5. API load testing

Environment: **local uvicorn** `src.api.main:app`, 1 worker, `127.0.0.1:8000`, synthetic UCI-shaped JSON.
Guard: `--min-free-mb 350`. Duration 8 s/level.

| Concurrency | RPS | p50 ms | p95 ms | p99 ms | Errors | Timeouts |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | **54.75** | 15.3 | 29.7 | 43.2 | 0 | 0 |
| 2 | 49.50 | 38.7 | 54.7 | 66.1 | 0 | 0 |
| 4 | 47.13 | 84.2 | 116.6 | 157.8 | 0 | 0 |
| 8 | 45.38 | 175.9 | 235.0 | 251.2 | 0 | 0 |

Saturation: RPS peaks at concurrency **1**; latency scales with concurrency (single-worker bound).
Safe working band for low-latency: concurrency **1–2**; up to **4** if p95≈120 ms acceptable.
Health `/live` + `/ready` **200** after test. Status: **VERIFIED_LOCAL** (not cloud).

---

## 6. GPU benchmark

| Layer | Status |
| --- | --- |
| Local laptop | **BLOCKED_NO_GPU** |
| Hardened Colab (T4) | **VERIFIED_GPU** — `results/block7/colab/hardened/` (30 configs, 9000 timed, parity PASS, 8/8 CUDA Node events) |
| Historical Colab (earlier runner) | Kept separate under `results/block7/colab/` |
| Quantized GPU | **NOT_EXECUTED** |

Finding (hardened, do not alter): ONNX FP32 CPU p50 faster than CUDA by ~2.65×–5.24× for batches 1–128.

---

## 7. Production resource configuration

See `docs/production_resource_sizing.md`.
**Keep** staging/production resource patches and `ORT_INTRA_OP_THREADS=2`.
Default serving model: **ONNX FP32**. GPU node group remains off. Quantized not promoted.

---

## 8. Artifacts

**Git-tracked (visible after `git clone`):** [`results/block7/`](../results/block7/)

- `parity_summary.json`, `quality_fp32_vs_quant.json`
- `cpu_benchmark_model_only.csv` / `.json`, `cpu_thread_probe.csv`
- `api_load_summary.json`, `gpu_status.json`, `run_metadata.json`
- plots: `plot_*.png`

Local working copies (gitignored): `artifacts/block7/` full JSON.

Utilities: `scripts/block7_eval.py`, `scripts/api_load_test.py`, `tests/nn/*`.

---

## 9. Gaps / honesty

1. GPU inference **not measured** — Blocked.
2. API load is laptop uvicorn, not Managed K8s.
3. Quantization does **not** reliably accelerate this CPU path.
4. MLP still slightly below RF baseline ROC-AUC (unchanged historical fact).
5. Concurrent levels 16 skipped deliberately under low free RAM.

---

## Historical Stage 1 audit snapshot (2026-11-22)

Earlier Stage 1 technical audit recorded leakage/parity/quant/CPU checks as PASS on that date (pytest 35 for NN suite at the time). Canonical metrics and tables: `docs/model_benchmark.md` and `results/block7/`.
