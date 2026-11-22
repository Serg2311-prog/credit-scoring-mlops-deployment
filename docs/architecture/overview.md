# Архитектура (черновик этапа 0)

Провайдер IaC: **Yandex Cloud**.  
Инференс по умолчанию (целевой): **ONNX Runtime CPU**.  
Baseline сравнения: **RandomForest** из исходного проекта (метрики зафиксированы исторически).

```mermaid
flowchart TB
  subgraph Data["Data layer"]
    CSV["UCI CSV + DVC"]
    PREP["prepare / Pandera"]
    TRAINCSV["train.csv / test.csv"]
    CSV --> PREP --> TRAINCSV
  end

  subgraph Train["Training"]
    FE["FeatureEngineer"]
    SKPRE["sklearn ColumnTransformer"]
    RF["Baseline RF Pipeline"]
    NN["PyTorch MLP"]
    ONNX["ONNX + dynamic quant"]
    TRAINCSV --> FE --> SKPRE
    SKPRE --> RF
    SKPRE --> NN --> ONNX
  end

  subgraph Serve["Serving"]
    API["FastAPI backend"]
    UI["Minimal frontend"]
    AB["A/B router"]
    UI --> API --> AB
    AB --> RF
    AB --> ONNX
  end

  subgraph Obs["Observability"]
    PROM["Prometheus"]
    GRAF["Grafana"]
    LOKI["Loki"]
    API --> PROM
    API --> LOKI
    PROM --> GRAF
  end

  subgraph Ops["Ops"]
    TF["Terraform YC modules"]
    K8S["Managed Kubernetes"]
    GHA["GitHub Actions"]
    AF["Airflow retrain DAG"]
    EV["Evidently drift"]
    TF --> K8S
    GHA --> K8S
    AF --> Train
    EV --> AF
  end
```

Подробный план: [`../implementation_plan.md`](../implementation_plan.md).  
Матрица требований: [`../requirements_matrix.md`](../requirements_matrix.md).
