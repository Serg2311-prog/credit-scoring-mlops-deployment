# API Contract — Credit Scoring Inference

**Backend:** ONNX Runtime CPU FP32 (`mlp-onnx-fp32-v1`)  
**Threshold:** `0.5` (как в `params.yaml` / этапе 1)  
**Input features:** 23 raw UCI columns (без `ID`, без target)  
**Preprocessed dim:** 47

OpenAPI: `http://127.0.0.1:8000/docs`

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health/live` | Liveness (процесс жив) |
| GET | `/health/ready` | Readiness (модель+preprocessor загружены) |
| GET | `/model/info` | Безопасные метаданные модели |
| POST | `/predict` | Один клиент |
| POST | `/predict/batch` | Пакет клиентов (`items`, max 256) |
| GET | `/metrics` | Prometheus metrics |

## Request body (`/predict`)

Поля и ограничения согласованы с Pandera (`src/data/validation.py`):

- `LIMIT_BAL` float ≥ 0
- `SEX` ∈ {1,2}
- `EDUCATION` ∈ {0..6}
- `MARRIAGE` ∈ {0..3}
- `AGE` ∈ [18,100]
- `PAY_0..PAY_6` ∈ [-2,8]
- `BILL_AMT1..6` finite float
- `PAY_AMT1..6` float ≥ 0
- extra fields запрещены (`extra=forbid`)
- NaN/Infinity запрещены

## Response

```json
{
  "probability_default": 0.830205,
  "prediction": 1,
  "model_version": "mlp-onnx-fp32-v1",
  "request_id": "..."
}
```

`prediction = 1` если `probability_default >= 0.5`.

## Errors

| HTTP | error_code | Когда |
| ---: | --- | --- |
| 422 | validation_error / batch_limit_exceeded | Невалидный JSON/поля/batch |
| 503 | model_not_ready | Нет артефактов / runtime не загружен |
| 500 | inference_error / internal_error | Сбой inference (без traceback клиенту) |

## Pipeline

`JSON → Pydantic → FeatureEngineer → sklearn preprocessor.joblib → ONNX FP32 → sigmoid → response`
