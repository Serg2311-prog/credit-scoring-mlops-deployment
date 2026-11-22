"""FastAPI application: credit scoring ONNX inference."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from src.api import dependencies
from src.api.errors import AppError, ModelNotReadyError
from src.api.logging_config import configure_logging
from src.api.metrics import (
    BATCH_SIZE,
    INFERENCE_COUNT,
    MODEL_READY,
    REQUEST_COUNT,
    REQUEST_ERRORS,
    REQUEST_LATENCY,
    render_metrics,
)
from src.api.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    ClientFeatures,
    ErrorResponse,
    HealthResponse,
    ModelInfoResponse,
    PredictResponse,
    ReadyResponse,
)
from src.api.settings import get_settings

LOGGER = logging.getLogger("src.api")


def _request_id(request: Request) -> str:
    existing = request.headers.get("x-request-id")
    if existing:
        return existing[:128]
    return str(uuid.uuid4())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    MODEL_READY.set(0)
    try:
        dependencies.init_runtime(settings)
        MODEL_READY.set(1)
    except Exception:  # noqa: BLE001
        MODEL_READY.set(0)
        LOGGER.exception("Startup model load failed; service stays up for /live")
    yield
    dependencies.shutdown_runtime()
    MODEL_READY.set(0)


app = FastAPI(
    title="Credit Scoring Inference API",
    description=(
        "ONNX FP32 credit default scoring. "
        "Input: raw UCI client features. Output: default probability and decision."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def metrics_and_logging_middleware(request: Request, call_next):
    request_id = _request_id(request)
    request.state.request_id = request_id
    started = time.perf_counter()
    endpoint = request.url.path
    method = request.method
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        status_code = 500
        raise
    finally:
        latency_s = time.perf_counter() - started
        latency_ms = round(latency_s * 1000.0, 3)
        # Avoid high-cardinality labels: only coarse endpoint path.
        label_endpoint = endpoint if endpoint.count("/") <= 3 else "/other"
        REQUEST_COUNT.labels(method, label_endpoint, str(status_code)).inc()
        REQUEST_LATENCY.labels(method, label_endpoint).observe(latency_s)
        if status_code >= 400:
            REQUEST_ERRORS.labels(method, label_endpoint, str(status_code)).inc()
        LOGGER.info(
            "request completed",
            extra={
                "request_id": request_id,
                "endpoint": endpoint,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "model_version": get_settings().model_version,
            },
        )


def _error_payload(
    request: Request, *, error_code: str, message: str, details: Any = None
) -> dict[str, Any]:
    return ErrorResponse(
        error_code=error_code,
        message=message,
        request_id=getattr(request.state, "request_id", _request_id(request)),
        details=details,
    ).model_dump()


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            request,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            request,
            error_code="validation_error",
            message="Request validation failed",
            details=exc.errors(),
        ),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    LOGGER.exception("Unhandled error", extra={"request_id": _request_id(request)})
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            request,
            error_code="internal_error",
            message="Internal server error",
        ),
    )


@app.get("/health/live", response_model=HealthResponse)
def health_live() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get(
    "/health/ready",
    response_model=ReadyResponse,
    responses={503: {"model": ErrorResponse}},
)
def health_ready(request: Request) -> ReadyResponse:
    runtime = dependencies.get_runtime_optional()
    if runtime is None or not runtime.ready:
        raise ModelNotReadyError(
            (runtime.load_error if runtime else None) or "Model runtime is not ready"
        )
    return ReadyResponse(
        status="ready",
        model_loaded=True,
        preprocessor_loaded=True,
        backend=runtime.backend,
        model_version=runtime.model_version,
    )


@app.get(
    "/model/info",
    response_model=ModelInfoResponse,
    responses={503: {"model": ErrorResponse}},
)
def model_info() -> ModelInfoResponse:
    runtime = dependencies.get_runtime()
    info = runtime.info()
    return ModelInfoResponse(
        model_name=info["model_name"],
        model_version=info["model_version"],
        backend=info["backend"],
        model_format=info["model_format"],
        input_features_count=info["input_features_count"],
        threshold=info["threshold"],
        max_batch_size=info["max_batch_size"],
    )


@app.post(
    "/predict",
    response_model=PredictResponse,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def predict(payload: ClientFeatures, request: Request) -> PredictResponse:
    runtime = dependencies.get_runtime()
    request_id = getattr(request.state, "request_id", _request_id(request))
    result = runtime.predict_records([payload.model_dump()])
    INFERENCE_COUNT.labels("/predict").inc()
    BATCH_SIZE.observe(1)
    return PredictResponse(
        probability_default=round(float(result.probabilities[0]), 6),
        prediction=int(result.predictions[0]),
        model_version=runtime.model_version,
        request_id=request_id,
    )


@app.post(
    "/predict/batch",
    response_model=BatchPredictResponse,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def predict_batch(
    payload: BatchPredictRequest, request: Request
) -> BatchPredictResponse:
    settings = get_settings()
    if len(payload.items) > settings.max_batch_size:
        raise AppError(
            f"Batch size {len(payload.items)} exceeds MAX_BATCH_SIZE="
            f"{settings.max_batch_size}",
            status_code=422,
            error_code="batch_limit_exceeded",
            details={"max_batch_size": settings.max_batch_size},
        )
    runtime = dependencies.get_runtime()
    request_id = getattr(request.state, "request_id", _request_id(request))
    records = [item.model_dump() for item in payload.items]
    result = runtime.predict_records(records)
    INFERENCE_COUNT.labels("/predict/batch").inc()
    BATCH_SIZE.observe(len(records))
    responses = [
        PredictResponse(
            probability_default=round(float(prob), 6),
            prediction=int(pred),
            model_version=runtime.model_version,
            request_id=request_id,
        )
        for prob, pred in zip(result.probabilities, result.predictions, strict=True)
    ]
    return BatchPredictResponse(
        results=responses,
        model_version=runtime.model_version,
        request_id=request_id,
        batch_size=len(responses),
    )


@app.get("/metrics")
def metrics() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "credit-scoring-inference",
        "docs": "/docs",
        "live": "/health/live",
        "ready": "/health/ready",
        "predict": "/predict",
        "metrics": "/metrics",
    }
