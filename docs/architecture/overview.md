# Архитектура системы

**Проект:** credit-scoring-mlops-deployment
**Тема:** промышленное развёртывание кредитной скоринговой системы с полным MLOps-циклом
**Документационный baseline релиза:** commit `5527a55` / tag `v1.0.0` (исторические Block 9 формулировки ниже обновлены по фактам Block 11).

Документ описывает **фактически реализованные** компоненты.

Уровни проверки: **STATIC / LOCAL / CLOUD_INFRA / CLOUD_APP / OPS**.
**CLOUD_INFRA (Block 11):** Yandex Managed Kubernetes experiment — Remote State + Apply + Ready worker + Calico + Metrics Server **runtime verified**, затем **destroy verified**.
**CLOUD_APP:** `ABORT_CLOUD_APP` (локальные images/smoke/parity; cloud deploy не выполнялся). Детали: [`results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](../../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md).

---

## 1. Общая архитектура системы

```mermaid
flowchart TB
  subgraph clients [Clients]
    UI[Frontend nginx :8081]
    HTTP[HTTP / curl / tests]
  end

  subgraph serving [Inference - local verified]
    API[FastAPI ONNX Runtime CPU FP32]
    PRE[preprocessor.joblib]
    ONNX[credit_scoring_nn.onnx]
    MET[/metrics Prometheus/]
    LOGS[JSON stdout logs]
  end

  subgraph obs [Observability - local verified]
    PROM[Prometheus]
    GRAF[Grafana]
    LOKI[Loki]
    ALLOY[Grafana Alloy]
    AM[Alertmanager]
    WH[alert-webhook sink]
  end

  subgraph offline [Offline MLOps - local verified]
    EV[Evidently data drift]
    AB[A/B router + offline compare]
    REG[model_registry.json]
    AF[Airflow DAG retraining]
  end

  subgraph iac [Cloud IaC - Block 11 infra verified then destroyed]
    TF[Terraform Yandex Cloud modules]
    K8Scloud[MK8s experiment apply then destroy]
  end

  subgraph localk8s [Local K8s - kind verified]
    KIND[kind + Ingress + NetworkPolicy]
  end

  UI --> API
  HTTP --> API
  API --> PRE --> ONNX
  API --> MET --> PROM --> GRAF
  API --> LOGS --> ALLOY --> LOKI
  LOKI --> AM --> WH
  PROM --> AM
  EV --> AF
  AB --> REG
  TF -.-> K8Scloud
  KIND --> API
```

**Легенда:** сплошные стрелки — локально проверенный runtime; пунктир — cloud path (infra Block 11 verified+destroyed; app ABORT).

---

## 2. Inference pipeline

```mermaid
flowchart LR
  REQ[POST /predict] --> VAL[Pydantic ClientFeatures]
  VAL --> FE[FeatureEngineer]
  FE --> JOB[preprocessor.joblib]
  JOB --> ORT[ONNX Runtime CPU FP32]
  ORT --> OUT[probability + prediction + model_version]
  REQ --> RID[X-Request-ID]
  RID --> ABrot{AB_ENABLED?}
  ABrot -->|no default| ORT
  ABrot -->|yes experimental| SPLIT[champion ONNX / challenger quant ONNX]
  SPLIT --> OUT
```

Контракт: [`docs/api_contract.md`](../api_contract.md).
Production serving по умолчанию: **ONNX FP32**, `AB_ENABLED=false`, `auto_promote=false`.

---

## 3. CI/CD pipeline

```mermaid
flowchart TB
  PUSH[push / PR] --> ORCH[ci-cd.yml orchestrator]
  ORCH --> PY[ci-python: pytest black flake8]
  ORCH --> DOCK[ci-docker: build + Trivy]
  ORCH --> INF[ci-infrastructure: terraform validate]
  ORCH --> K8S[ci-kubernetes: kubeconform]
  ORCH --> AFCI[ci-airflow-dag: DAG import]
  ORCH --> GATE{5/5 gates}
  GATE -->|validation| DONE[report]
  GATE -->|publish opt-in| GHCR[GHCR digests]
  GATE -->|deploy dry-run| CD[cd-staging dry-run]
  MANUAL[workflow_dispatch] --> RC[release-candidate]
  MANUAL --> CDP[cd-production promote digests]
```

Hosted cloud **app** deploy и `terraform apply` в CI **не выполняются**. Experiment infra apply выполнен оператором вне CI (Block 11).

---

## 4. Monitoring and alerting pipeline

```mermaid
flowchart LR
  API2[API /metrics] --> P2[Prometheus]
  CAD[cAdvisor] --> P2
  DEX[drift-metrics-exporter optional E2E] --> P2
  P2 --> G2[Grafana]
  P2 --> R2[Prometheus rules]
  API3[API JSON logs] --> A3[Alloy]
  PROBE[e2e-log-probe test-only] --> A3
  A3 --> L3[Loki]
  L3 --> LR[Loki Ruler]
  R2 --> AM2[Alertmanager]
  LR --> AM2
  AM2 --> WH2[local webhook]
```

Production API **не** содержит `/internal/e2e/log-error`. Test-only probe — только E2E overlay.

---

## 5. Drift detection and retraining lifecycle

```mermaid
flowchart TB
  REF[reference features] --> DR[Evidently data drift]
  CUR[current features] --> DR
  LAB[labeled scores] --> QD[quality / degradation signal]
  DR --> TRIG[evaluate_triggers]
  QD --> TRIG
  TRIG -->|skipped| SKIP[no retrain]
  TRIG -->|triggered| CAND[train candidate in isolated run dir]
  CAND --> EVAL[holdout metrics vs champion]
  EVAL --> DEC{auto_promote?}
  DEC -->|false always here| HOLD[candidate artifacts only]
  DEC -.->|not enabled| PROMO[production rewrite]
```

Concept drift в production **не** утверждается только по падению ROC-AUC. Контролируемый synthetic experiment (Block 8.1) отделён от production diagnostics.

---

## 6. Cloud infrastructure (IaC, not applied)

```mermaid
flowchart TB
  subgraph staging [staging env - separate state]
    SN[network VPC]
    SK[Managed K8s CPU]
    SS[Object Storage]
    SR[Container Registry]
    SM[logging / monitoring stubs]
  end
  subgraph production [production env - separate state]
    PN[network VPC]
    PK[Managed K8s CPU]
    PS[Object Storage]
  end
  OPS[Operator laptop] -->|terraform validate / plan| staging
  OPS -->|cloud-experiment apply DONE| expCloud[Yandex MK8s experiment]
  OPS -.->|CLOUD_APP pending| expCloud
  GPU[GPU node group] -.->|enable_gpu_node_group=false default| SK
```

Модули: `infra/terraform/modules/{network,iam,kubernetes,registry,storage,monitoring}`.

---

## 7. Model registry and A/B routing

```mermaid
flowchart LR
  REG2[models/model_registry.json production] --> CHAMP[champion ONNX FP32]
  DEMO[artifacts/monitoring/demo_model_registry.json] --> OFFAB[offline A/B demo]
  CHAMP --> API4[API default]
  QONNX[quant.onnx experimental challenger] --> ABE[AB overlay compose]
  CHAMP --> ABE
  ABE --> HASH[hash unit_id + salt]
  HASH --> W[traffic weights]
```

Demo CLI **не** пишет в production registry (Block 8.1). Online A/B — изолированный compose, synthetic HTTP.

---

## Связанные документы

- [`../terraform_infrastructure.md`](../terraform_infrastructure.md)
- [`../cicd_pipeline.md`](../cicd_pipeline.md)
- [`../docker_deployment.md`](../docker_deployment.md)
- [`../kubernetes_local_deployment.md`](../kubernetes_local_deployment.md)
- [`observability.md`](observability.md)
- [`../stage5_runbook.md`](../stage5_runbook.md)
- [`../stage6_runbook.md`](../stage6_runbook.md)
- [`../stage7_runbook.md`](../stage7_runbook.md)
