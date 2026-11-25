"""Prometheus metrics for inference API.

Drift / offline quality gauges live on ``drift-metrics-exporter`` only.
Unset gauges here would default to 0 and look like «no drift».
"""

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
ML_AB_EXPERIMENT_SAMPLES = Counter(
    "ml_ab_experiment_samples",
    "Prediction samples routed in A/B experiment",
    ["ab_group"],
    registry=REGISTRY,
)


def observe_ab_sample(ab_group: str) -> None:
    group = "challenger" if ab_group == "challenger" else "champion"
    ML_AB_EXPERIMENT_SAMPLES.labels(group).inc()


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
