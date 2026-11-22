# Архитектура

Провайдер IaC (позже): **Yandex Cloud** (пока только план).  
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

## Stage 3A — Local Kubernetes (kind)

```mermaid
flowchart TB
  Host[Windows + Docker Desktop] --> Kind[kind control-plane]
  Kind --> NS[Namespace credit-scoring]
  NS --> CM[ConfigMap]
  NS --> DEP[Deployment replicas=1]
  NS --> SVC[Service ClusterIP]
  DEP --> INIT[initContainer copy-models]
  DEP --> CTR[api container]
  INIT --> Vol[emptyDir /app/models]
  CTR --> Vol
  User[Developer] -->|port-forward| SVC
```

- Образы: `credit-scoring-api:stage3a`, `credit-scoring-models:stage3a` (kind load).
- Без Ingress / mesh / cloud / Prometheus Operator.
- Probes: live → liveness/startup; ready → readiness.
- Overlay: `k8s/overlays/local`.

Подробности API: [`../api_contract.md`](../api_contract.md)  
Docker: [`../docker_deployment.md`](../docker_deployment.md)  
Kubernetes: [`../kubernetes_local_deployment.md`](../kubernetes_local_deployment.md)
