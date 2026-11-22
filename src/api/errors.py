"""Ошибки API без утечки внутренних traceback клиенту."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "app_error",
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class ValidationAppError(AppError):
    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            message,
            status_code=422,
            error_code="validation_error",
            details=details,
        )


class ModelNotReadyError(AppError):
    def __init__(self, message: str = "Model runtime is not ready") -> None:
        super().__init__(
            message,
            status_code=503,
            error_code="model_not_ready",
        )


class InferenceError(AppError):
    def __init__(self, message: str = "Inference failed") -> None:
        super().__init__(
            message,
            status_code=500,
            error_code="inference_error",
        )
