# Stage 2 Validation Report — Inference API + Docker

**Date:** 2026-11-22  
**Scope:** FastAPI ONNX FP32 serving + Docker Compose only  
**Not done:** Kubernetes, Terraform, Airflow, cloud, git commit/push

## Acceptance criteria

| Criterion | Result | Evidence |
| --- | --- | --- |
| FastAPI starts locally | **PASS** | uvicorn on `127.0.0.1:8000` |
| ONNX FP32 on real artifacts | **PASS** | `preprocessor.joblib` + `credit_scoring_nn.onnx` |
| Input contract matches training | **PASS** | same `RAW_FEATURE_COLUMNS` + Pandera ranges |
| `/predict` and `/predict/batch` correct | **PASS** | local + Docker smoke; integration parity tests |
| Invalid requests predictable | **PASS** | 422 validation tests |
| Health/readiness | **PASS** | live 200; ready 200/503 |
| Prometheus metrics | **PASS** | `/metrics` exporters |
| Docker image builds | **PASS** | `build_exit=0` |
| Compose runs service | **PASS** | container `healthy` |
| API works in container | **PASS** | Docker smoke OK |
| pytest / flake8 / black | **PASS** | 57 passed / 0 / 0 |
| E2E API↔ONNX parity | **PASS** | `tests/api/test_integration_onnx.py` |
| Docs with real results | **PASS** | this file + api/docker docs |

## Quality gates

```text
pytest  -> 57 passed
flake8  -> 0
black   -> 0
```

## Example responses (real)

Local/Docker identical for sample client:

```json
{
  "probability_default": 0.830205,
  "prediction": 1,
  "model_version": "mlp-onnx-fp32-v1"
}
```

## HTTP API benchmark (local uvicorn)

Warmup=3, timed=15. Includes validation+FE+preprocess+ONNX+JSON (not stage-1 model-only).

| Batch | p50 ms | p95 ms | Throughput samples/s |
| ---: | ---: | ---: | ---: |
| 1 | 16.37 | 19.04 | 59.6 |
| 16 | 18.77 | 25.11 | 815 |
| 64 | 20.81 | 28.64 | 2964 |
| 256 | 25.21 | 34.55 | 9411 |

- Local uvicorn RSS ≈ **197.8 MB**
- Docker container memory ≈ **139.7 MiB**
- Cold start: app ready in a few seconds after container start; health status became `healthy`

## Known issues / notes

1. Local Python is 3.13; Docker uses 3.12-slim (intentional stable runtime).
2. Compose `deploy.resources` replaced with `mem_limit`/`cpus` for desktop compose.
3. Quantized ONNX not used for serving (stage-1 recommendation preserved).
4. No stage-1 errors requiring retrain were found for serving path.

## Readiness for stage 3

Ready for Kubernetes manifests using existing `/health/*` and `/metrics`.  
Do **not** start stage 3 until explicit approval.
