# GPU benchmark — Colab evidence (historical + hardened)

## Status layers

| Layer | Status | Location |
| --- | --- | --- |
| Local laptop | `BLOCKED_NO_GPU` | no CUDA |
| Historical Colab (Block 7.2 runner) | `VERIFIED_GPU_HISTORICAL_COLAB` | [`results/block7/colab/`](../results/block7/colab/) |
| **Hardened Colab (Block 7.3/7.4 runner)** | **`VERIFIED_GPU`** | [`results/block7/colab/hardened/`](../results/block7/colab/hardened/) |

Do **not** mix measurement tables across the two Colab experiments.

## Hardened VERIFIED_GPU (authoritative for current runner)

- Tesla T4, CUDA 13.0, PyTorch 2.14.1+cu130, ORT 1.32.0, threads=2
- 30 configs, 9000 timed measurements, parity **PASS**
- ORT profile: 8/8 Node events on `CUDAExecutionProvider`, 0 CPU
- `session.disable_cpu_ep_fallback=1` + `disable_fallback()` in runner
- Separate profiling session (not inside latency timings)
- Finding: **ORT FP32 CPU p50 ~2.65×–5.24× faster than ORT CUDA** (batches 1–128)
- Max ORT CPU throughput ≈ **1.99e6 samples/s** at batch=128 (**not** HTTP RPS)
- Quantized GPU: **NOT_EXECUTED**

Evidence: `results/block7/colab/hardened/`.
Runner used: `results/block7/colab/hardened/runner_used/` (SHA in `SHA256SUMS.json`).

### Hardened model_only p50 (ms)

| Batch | PT CPU | PT CUDA | ORT CPU | ORT CUDA |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.15042 | 0.37429 | **0.01966** | 0.10087 |
| 8 | 0.17811 | 0.31522 | **0.01946** | 0.10200 |
| 32 | 0.19419 | 0.33113 | **0.02608** | 0.12845 |
| 64 | 0.19277 | 0.32517 | **0.03808** | 0.14349 |
| 128 | 0.24009 | 0.32341 | **0.06248** | 0.16529 |

## Non-claims

- Synthetic model-only ≠ holdout quality
- Model throughput ≠ HTTP API throughput
- No GPU INT8, no GPU API load, no cloud GPU nodes provisioned
- Colab CPU model string not recorded in environment JSON

## Production implication

Prefer **ONNX FP32 CPU** for this MLP. GPU node group remains optional.
No production registry / model / Kubernetes resource changes.

## Package rebuild (optional)

```bash
python scripts/gpu_benchmark/package_zip.py
```

Cells: `scripts/gpu_benchmark/COLAB_CELLS.md`.
