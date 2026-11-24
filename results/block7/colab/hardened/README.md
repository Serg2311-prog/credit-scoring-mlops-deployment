# Hardened Colab GPU evidence (Block 7.4) — VERIFIED_GPU

## Origin

- **Where:** Google Colab, NVIDIA Tesla T4, CUDA 13.0
- **Software:** PyTorch 2.14.1+cu130, ONNX Runtime 1.32.0, CPU threads=2
- **Runner:** `scripts/gpu_benchmark/run_benchmark.py` (`hardened_block73`)
- **Runner SHA256:** see `SHA256SUMS.json` (`runner_sha256`); byte-identical to project source at integration time
- **Date:** 2026-11-24 (profile `15-38-33`)

This directory is **separate** from the historical Block 7.2 experiment in
`results/block7/colab/` (parent). Do **not** mix measurement tables across runners.

## Scope / non-claims

| This evidence is | This evidence is **not** |
| --- | --- |
| Synthetic model-only latency/throughput | Holdout quality evaluation |
| Model samples/s on Colab CPU/GPU | HTTP API RPS / load test |
| Separate ORT CUDA profiling session | Profiling overhead inside latency timings |
| FP32 PyTorch + ORT CPU/CUDA | GPU INT8 / quantized inference |
| Laptop+Colab notebook proof | Deployed cloud GPU node proof |

CPU model string on Colab host was **not** recorded in the JSON environment block.

## Experiment

| Item | Value |
| --- | --- |
| Batch sizes | 1, 8, 32, 64, 128 |
| Warmup / timed / repeats | 20 / 100 / 3 |
| Configurations | 30 |
| Timed measurements | 9000 |
| GPU status | **VERIFIED_GPU** |
| Parity | **PASS** |
| ORT Node events | 8 CUDA / 0 CPU / 0 missing provider |
| Quantized GPU | **NOT_EXECUTED** |

## Key finding (hardened measurements)

ONNX Runtime FP32 **CPU** p50 is faster than ORT CUDA by about **2.65×–5.24×** for batches 1–128 on this MLP/T4.

Prefer **ONNX FP32 CPU** for production serving of this model. GPU node group remains optional. Production registry/models/K8s resources unchanged.

## Files

| File | Role |
| --- | --- |
| `colab_gpu_benchmark.json` / `.csv` | Original hardened results |
| `onnxruntime_profile__*.json` | Single original ORT profile (duplicate in archive dropped) |
| `experiment_config.json` | Settings |
| `synthetic_features_meta.json` | Synthetic input meta + SHA256 |
| `runner_used/` | Exact runner/mlp used in the run |
| `plots/` | Charts derived from this JSON only |
| `SHA256SUMS.json` | Integrity manifest |
