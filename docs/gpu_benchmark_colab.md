# GPU benchmark — external runner (Google Colab / any CUDA host)

Local laptop status: **BLOCKED_NO_GPU** (`torch.cuda.is_available()==False`).
Do **not** treat CPU latency as GPU results.
Tracked evidence: [`results/block7/gpu_status.json`](../results/block7/gpu_status.json).

## Goal

Produce a real `artifacts/benchmark_gpu.json` (and optionally copy into
`results/block7/gpu_status.json`) with `"status": "completed"` on a machine that has CUDA.

## Runner guarantees (`python -m src.nn.benchmark --device cuda`)

| Check | Behavior |
| --- | --- |
| Explicit device | `--device cuda` (alias `gpu`) |
| `torch.cuda.is_available()` | Required; else `BLOCKED_NO_GPU` |
| `CUDAExecutionProvider` in ORT | Required; else `BLOCKED_NO_GPU` |
| Silent CPU fallback | **Forbidden** — `allow_cpu_fallback` raises; no CPU latency under GPU label |
| Model placement | Checkpoint moved to `cuda`; fails if parameter device ≠ cuda |
| Synchronization | `torch.cuda.synchronize()` around timed forward |
| Warm-up | Same as CPU (`warmup_runs` from `params.yaml`, default 20) |
| Inputs | Same holdout feature matrix as CPU path |
| Output format | JSON with `status`, `results` rows (p50/p95/p99, throughput, repeats) |

## Colab sketch (operator runs manually — not automated from this repo)

1. Upload or clone the project (minimum: `models/*.pt`, `models/*.onnx`,
   `data/processed/test.csv` or regenerate, `params.yaml`, `src/`).
2. Runtime → **GPU**.
3. Install deps (GPU builds of torch / onnxruntime as available):

```bash
pip install torch onnxruntime-gpu onnx pandas scikit-learn joblib pyyaml psutil
```

4. Verify before measuring:

```python
import torch, onnxruntime as ort
assert torch.cuda.is_available(), "no CUDA"
assert any("CUDA" in p for p in ort.get_available_providers()), "no CUDA EP"
print(torch.cuda.get_device_name(0))
print(ort.get_available_providers())
```

5. Run:

```bash
export PYTHONPATH=.
python -m src.nn.benchmark --device cuda --batch-sizes 1,8,32,64,128 \
  --output artifacts/benchmark_gpu.json
```

6. Confirm JSON has `"status": "completed"` and a non-empty `results` list.
   Copy anonymized summary into `results/block7/gpu_status.json` only from that file.
   Append measured numbers to `docs/model_benchmark.md` only from that file.

7. Download the JSON from Colab if the runtime is ephemeral.

## Policy

- No silent CPU fallback when `--device cuda`.
- Do not commit Colab credentials or personal data.
- Until a real GPU run exists, status remains **BLOCKED_NO_GPU** / not `VERIFIED_GPU`.
