"""Shared runtime holder for FastAPI lifespan."""

from __future__ import annotations

from src.api.errors import ModelNotReadyError
from src.api.inference import OnnxInferenceRuntime
from src.api.settings import Settings, get_settings

_runtime: OnnxInferenceRuntime | None = None


def init_runtime(settings: Settings | None = None) -> OnnxInferenceRuntime:
    global _runtime
    cfg = settings or get_settings()
    runtime = OnnxInferenceRuntime(cfg)
    runtime.load()
    _runtime = runtime
    return runtime


def shutdown_runtime() -> None:
    global _runtime
    _runtime = None


def get_runtime() -> OnnxInferenceRuntime:
    if _runtime is None or not _runtime.ready:
        raise ModelNotReadyError("Model runtime is not ready")
    return _runtime


def get_runtime_optional() -> OnnxInferenceRuntime | None:
    return _runtime
