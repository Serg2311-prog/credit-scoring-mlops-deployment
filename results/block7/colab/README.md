# Colab GPU evidence (historical Block 7.2 / 7.3)

## Origin

- **Where:** Google Colab, NVIDIA Tesla T4, CUDA 13.0
- **Software:** PyTorch 2.14.1+cu130, ONNX Runtime 1.32.0
- **Runner:** `historical_runner/run_benchmark.py` + `mlp_model.py` (exact copies used in the experiment)
- **Date:** 2026-11-24 (profile timestamp `15-19-30`)

## Scope

**Model-only synthetic latency/throughput** on `float32[1024,47]`, seed 42.

This is **not**:

- holdout quality evaluation (see `results/block7/quality_fp32_vs_quant.json`)
- API load testing (see `results/block7/api_load_summary.json`)
- a validation of the **hardened** runner under `scripts/gpu_benchmark/` (requires a new GPU run)

## Experiment parameters

| Item | Value |
| --- | --- |
| Batch sizes | 1, 8, 32, 64, 128 |
| Warmup / timed / repeats | 20 / 100 / 3 |
| Configurations | 30 |
| Timed measurements | 9000 |
| Parity | PASS (atol 1e-5, rtol 1e-4) |
| Quantized GPU | **not executed** |

## Independent ORT profiling check

File: `onnxruntime_profile__2026-11-24_15-19-30_623.json`

- 12 events total
- 8 `cat=Node` events
- all 8 have `args.provider=CUDAExecutionProvider`
- 0 CPU Node events

## Key measured finding (do not alter)

For this small MLP and batches 1–128, **ONNX FP32 CPU p50 is faster than ONNX FP32 CUDA** by about **1.67×–5.32×**.

Production recommendation remains **ONNX FP32 CPU**; GPU node group stays optional.

## Files

| File | Role |
| --- | --- |
| `colab_gpu_benchmark.json` / `.csv` | Original measured results |
| `onnxruntime_profile__*.json` | Original ORT profile |
| `experiment_config.json` | Experiment settings |
| `synthetic_features_meta.json` | Synthetic input metadata + SHA256 |
| `historical_runner/` | Exact runner used for these numbers |
| `SHA256SUMS.json` | Evidence integrity manifest |
| `plots/` | Derived charts (from original JSON) |

## Hardened runner note

`scripts/gpu_benchmark/` improves fallback disable, structured profile parsing, IOBinding setup outside the timed loop, ZIP POSIX paths, and exit codes. **It has not been re-verified on GPU.** Historical numbers above remain the accepted Colab evidence.
