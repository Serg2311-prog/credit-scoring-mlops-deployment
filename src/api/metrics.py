"""Prometheus metrics for inference API."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()

REQUEST_COUNT = Counter(
    "credit_scoring_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)
REQUEST_ERRORS = Counter(
    "credit_scoring_http_errors_total",
    "Total HTTP error responses",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)
REQUEST_LATENCY = Histogram(
    "credit_scoring_http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)
INFERENCE_COUNT = Counter(
    "credit_scoring_inference_requests_total",
    "Inference calls",
    ["endpoint"],
    registry=REGISTRY,
)
INFERENCE_LATENCY = Histogram(
    "credit_scoring_inference_latency_seconds",
    "Model inference latency in seconds (preprocess + ONNX)",
    ["endpoint"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    registry=REGISTRY,
)
BATCH_SIZE = Histogram(
    "credit_scoring_batch_size",
    "Batch size distribution",
    buckets=(1, 2, 4, 8, 16, 32, 64, 128, 256),
    registry=REGISTRY,
)
MODEL_READY = Gauge(
    "credit_scoring_model_ready",
    "1 if model runtime is ready else 0",
    registry=REGISTRY,
)

# Stage 6 monitoring gauges/counters (low-cardinality labels only).
# Names follow the stage brief (`ml_*`) and live in the same registry as API metrics.
ML_DATA_DRIFT_SHARE = Gauge(
    "ml_data_drift_share",
    "Share of features with detected data drift (last offline check)",
    registry=REGISTRY,
)
ML_DATA_DRIFT_DETECTED = Gauge(
    "ml_data_drift_detected",
    "1 if last data-drift check crossed share threshold else 0",
    registry=REGISTRY,
)
ML_MODEL_ROC_AUC = Gauge(
    "ml_model_roc_auc",
    "Latest labeled ROC-AUC for the scored cohort",
    ["model_role"],
    registry=REGISTRY,
)
ML_MODEL_PR_AUC = Gauge(
    "ml_model_pr_auc",
    "Latest labeled PR-AUC for the scored cohort",
    ["model_role"],
    registry=REGISTRY,
)
ML_MODEL_F1 = Gauge(
    "ml_model_f1",
    "Latest labeled F1 for the scored cohort",
    ["model_role"],
    registry=REGISTRY,
)
ML_AB_EXPERIMENT_SAMPLES = Counter(
    "ml_ab_experiment_samples",
    "Prediction samples routed in A/B experiment",
    ["ab_group"],
    registry=REGISTRY,
)


def update_data_drift_metrics(*, drift_share: float, detected: bool) -> None:
    ML_DATA_DRIFT_SHARE.set(float(drift_share))
    ML_DATA_DRIFT_DETECTED.set(1.0 if detected else 0.0)


def update_model_quality_metrics(
    *,
    model_role: str,
    roc_auc: float | None = None,
    pr_auc: float | None = None,
    f1: float | None = None,
) -> None:
    # model_role: champion|challenger|production (keep cardinality tiny).
    role = str(model_role)
    if roc_auc is not None:
        ML_MODEL_ROC_AUC.labels(role).set(float(roc_auc))
    if pr_auc is not None:
        ML_MODEL_PR_AUC.labels(role).set(float(pr_auc))
    if f1 is not None:
        ML_MODEL_F1.labels(role).set(float(f1))


def observe_ab_sample(ab_group: str) -> None:
    group = "challenger" if ab_group == "challenger" else "champion"
    ML_AB_EXPERIMENT_SAMPLES.labels(group).inc()


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
