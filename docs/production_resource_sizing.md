# Production resource sizing (Block 7 / 7.1)

**Evidence class:** local laptop measurements (`VERIFIED_LOCAL`).
**Not** Kubernetes resource-limit proof. Local uvicorn RPS ≠ pod capacity under CPU/memory limits.

Hardware used for evidence: Intel Core i5-1135G7, 8 GB RAM, no GPU, Windows 11,
Python 3.13, torch 2.15.0+cpu, onnxruntime 1.32.0 (CPUExecutionProvider).

Git-tracked numbers: [`results/block7/`](../results/block7/).

---

## 1. Measured characteristics (local only)

| Signal | Observation | Source |
| --- | --- | --- |
| Model size | ONNX FP32 62934 B; quant 24223 B | `quality_fp32_vs_quant.json` |
| model_only ORT FP32 | batch=1 mean≈0.021 ms; threads=2 | `cpu_benchmark_model_only.csv` |
| end-to-end | batch=1 p50≈10.6 ms (preprocess-dominated) | `cpu_benchmark_e2e_highlight.json` |
| Thread probe | ORT FP32 strong at 1–2 threads (batch=32) | `cpu_thread_probe.csv` |
| API load | Peak ~54.8 RPS at c=1; declines as c↑; p95 grows | `api_load_summary.json` |
| API health after load | `/live` + `/ready` 200 | same |
| Process RSS (bench) | ~340–391 MB with torch imported | CPU CSV `peak_rss_mb_observed_row` |
| API CPU% | **NOT_MEASURED** | — |
| GPU | `BLOCKED_NO_GPU` | `gpu_status.json` |

Saturation (local, single uvicorn worker): RPS max at concurrency **1**, lower at 2/4/8 while latency rises — enough to say this process saturates beyond c=1 on this host. **Not** a profiled attribution to model vs preprocess vs HTTP.

---

## 2. Manifest values vs recommendations

| Parameter | Staging manifest | Production manifest | Engineering recommendation | Tied to measurement? |
| --- | --- | --- | --- | --- |
| CPU request | **100m** (`overlays/staging/patch-resources.yaml`) | **200m** (`overlays/production/patch-resources.yaml`) | Keep | Request is scheduling floor; not equal to local RPS |
| CPU limit | **1** | **1** | Keep | Local ORT uses 2 threads; 1 CPU limit is enough for this MLP |
| Memory request | **256Mi** | **384Mi** | Keep | Local uvicorn RSS historically ~200 MB class; bench RSS higher with torch in-process |
| Memory limit | **512Mi** | **768Mi** | Keep | Headroom above observed API RSS |
| Replicas | base **1** | **2** | Keep prod=2 | Horizontal scale; local load was 1 process |
| API workers / pod | not set (image default 1) | same | **1** uvicorn worker | Avoid CPU oversubscription under 1 CPU limit |
| ORT intra-op | ConfigMap **2** (`k8s/base/configmap.yaml`) | same | **2** | Matches thread probe preference |
| ORT inter-op | ConfigMap **1** | same | **1** | Keep |
| Model | FP32 ONNX path in ConfigMap | same | Keep FP32 default | Quant not faster on this CPU for API-shaped load; 2.18% flips |
| Load / replica (guidance) | — | — | ~40–55 synthetic RPS; client concurrency 1–2 for low latency | **Local uvicorn only** — re-measure in cluster |
| GPU | Terraform GPU off | same | Not required | `BLOCKED_NO_GPU` |

**Action:** no Kubernetes manifest changes in Block 7.1 — current overlays already align with measured evidence + conservative headroom.

---

## 3. Caveats

1. Do not treat local free-RAM-constrained runs as cloud SKU proof.
2. Re-run `scripts/api_load_test.py` against staging after deploy before locking SLOs.
3. Quantized model remains optional / non-default.
