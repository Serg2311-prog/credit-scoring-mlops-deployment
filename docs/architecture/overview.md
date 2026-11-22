# Архитектура

Провайдер IaC: **Yandex Cloud** (Terraform подготовлен на этапе 3Б; **apply не выполнялся**).
CI/CD: GitHub Actions workflows (этап 4); cloud deploy — только dry-run gate.
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

## Stage 3A — Local Kubernetes (kind)

```mermaid
flowchart TB
  Host[Windows + Docker Desktop] --> Kind[kind control-plane]
  Kind --> NS[Namespace credit-scoring]
  NS --> DEP[Deployment]
  NS --> SVC[Service ClusterIP]
  DEP --> INIT[initContainer models image]
  DEP --> CTR[api]
```

## Stage 3B — Terraform (Yandex Cloud, code only)

```mermaid
flowchart TB
  subgraph envs [Separate states]
    STG[staging root module]
    PROD[production root module]
  end
  STG --> NET[network]
  STG --> IAM[iam]
  STG --> K8S[kubernetes]
  STG --> CR[registry]
  STG --> S3[storage private]
  STG --> LOG[logging group]
  PROD --> NET2[network other CIDR]
  PROD --> IAM2[iam]
  PROD --> K8S2[kubernetes]
```

- Модули: `infra/terraform/modules/{network,iam,kubernetes,registry,storage,monitoring}`
- Окружения: `infra/terraform/environments/{staging,production}`
- Секреты только через env / gitignored tfvars
- Будущий scrape `/metrics` — отдельный агент/Prometheus (не автоматом Yandex Monitoring)

## Stage 4 — CI/CD

```mermaid
flowchart LR
  PR[PR / push main] --> Py[ci-python]
  PR --> Infra[ci-infrastructure]
  PR --> Dock[ci-docker]
  PR --> K8s[ci-kubernetes manifests]
  Manual[workflow_dispatch] --> RC[release-candidate]
  Manual --> CD[cd-staging dry-run]
  Synth[synthetic ONNX/joblib] --> Py
  Synth --> Dock
```

Подробности: [`../cicd_pipeline.md`](../cicd_pipeline.md), [`../terraform_infrastructure.md`](../terraform_infrastructure.md)
