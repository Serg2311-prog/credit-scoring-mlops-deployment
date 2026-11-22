# Архитектура

Провайдер IaC (этап 2+): **Yandex Cloud** (пока только план).  
Инференс: **ONNX Runtime CPU FP32**.  
Baseline качества: RandomForest (исторический).

## Stage 2 — Inference path

```mermaid
flowchart LR
  Client[HTTP Client] --> API[FastAPI]
  API --> Val[Pydantic validation]
  Val --> FE[FeatureEngineer]
  FE --> PRE[preprocessor.joblib]
  PRE --> ORT[ONNX Runtime CPU FP32]
  ORT --> RESP[probability + prediction]
  API --> PROM[/metrics Prometheus/]
  API --> LOG[JSON logs]
```

Локальный Docker Compose поднимает только API (+ volume с артефактами).  
Observability stack / K8s / Terraform — следующие этапы.

Подробности API: [`../api_contract.md`](../api_contract.md)  
Docker: [`../docker_deployment.md`](../docker_deployment.md)
