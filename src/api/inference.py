"""ONNX FP32 runtime: trusted preprocessor + ONNX session."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.api.errors import InferenceError, ModelNotReadyError
from src.api.settings import Settings
from src.models.preprocessing import (
    preprocessor_input_dim,
    transform_features,
)
from src.schema import RAW_FEATURE_COLUMNS

LOGGER = logging.getLogger(__name__)


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64).reshape(-1)
    return 1.0 / (1.0 + np.exp(-logits))


@dataclass
class PredictionResult:
    probabilities: np.ndarray
    predictions: np.ndarray


class OnnxInferenceRuntime:
    """Загружает артефакты один раз. Без обучения, только CPU ORT."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model_path = settings.resolve_path(settings.model_path)
        self.preprocessor_path = settings.resolve_path(settings.preprocessor_path)
        self.threshold = float(settings.prediction_threshold)
        self.model_version = settings.model_version
        self.backend = settings.model_backend
        self._preprocessor = None
        self._session = None
        self._input_name: str | None = None
        self._input_dim: int | None = None
        self._ready = False
        self._load_error: str | None = None

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def input_dim(self) -> int | None:
        return self._input_dim

    def load(self) -> None:
        self._ready = False
        self._load_error = None
        try:
            if self.settings.model_backend.lower() != "onnx":
                raise RuntimeError(
                    f"Unsupported MODEL_BACKEND={self.settings.model_backend}"
                )
            if not self.preprocessor_path.is_file():
                raise FileNotFoundError(
                    f"Preprocessor not found: {self.preprocessor_path.name}"
                )
            if not self.model_path.is_file():
                raise FileNotFoundError(f"ONNX model not found: {self.model_path.name}")

            # joblib только из доверенного локального пути настроек.
            # FeatureEngineer должен быть импортируем через пакет src.
            from src.features import build_features as _build_features  # noqa: F401

            self._preprocessor = joblib.load(self.preprocessor_path)
            pre_dim = preprocessor_input_dim(self._preprocessor)

            import onnxruntime as ort

            so = ort.SessionOptions()
            so.intra_op_num_threads = int(self.settings.ort_intra_op_threads)
            so.inter_op_num_threads = int(self.settings.ort_inter_op_threads)
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=so,
                providers=["CPUExecutionProvider"],
            )
            inputs = self._session.get_inputs()
            if not inputs:
                raise RuntimeError("ONNX model has no inputs")
            self._input_name = inputs[0].name
            shape = inputs[0].shape
            # shape like [batch, features] or [None, 47]
            if len(shape) != 2:
                raise RuntimeError(f"Unexpected ONNX input rank: {shape}")
            onnx_dim = shape[1]
            if isinstance(onnx_dim, str) or onnx_dim is None:
                onnx_dim = int(self.settings.expected_input_dim)
            else:
                onnx_dim = int(onnx_dim)
            if pre_dim != onnx_dim:
                raise RuntimeError(
                    f"Preprocessor dim {pre_dim} != ONNX input dim {onnx_dim}"
                )
            if pre_dim != int(self.settings.expected_input_dim):
                raise RuntimeError(
                    f"Preprocessor dim {pre_dim} != EXPECTED_INPUT_DIM "
                    f"{self.settings.expected_input_dim}"
                )
            self._input_dim = pre_dim
            # Smoke transform/infer with zeros to fail fast.
            probe = np.zeros((1, pre_dim), dtype=np.float32)
            _ = self._session.run(None, {self._input_name: probe})
            self._ready = True
            LOGGER.info(
                "Model runtime loaded",
                extra={
                    "model_version": self.model_version,
                    "endpoint": "startup",
                },
            )
        except Exception as exc:  # noqa: BLE001 - сохраняем текст для readiness
            self._ready = False
            self._load_error = str(exc)
            LOGGER.exception("Failed to load model runtime")
            raise

    def require_ready(self) -> None:
        if not self._ready or self._session is None or self._preprocessor is None:
            raise ModelNotReadyError(self._load_error or "Model runtime is not ready")

    def _frame_from_records(self, records: list[dict[str, Any]]) -> pd.DataFrame:
        frame = pd.DataFrame(records)
        missing = [col for col in RAW_FEATURE_COLUMNS if col not in frame.columns]
        if missing:
            raise InferenceError(
                "Missing required features after validation: " + ", ".join(missing)
            )
        return frame.loc[:, list(RAW_FEATURE_COLUMNS)]

    def predict_records(self, records: list[dict[str, Any]]) -> PredictionResult:
        self.require_ready()
        assert self._preprocessor is not None
        assert self._session is not None
        assert self._input_name is not None
        try:
            frame = self._frame_from_records(records)
            matrix = transform_features(self._preprocessor, frame)
            if matrix.dtype != np.float32:
                matrix = matrix.astype(np.float32, copy=False)
            if matrix.ndim != 2 or matrix.shape[1] != self._input_dim:
                raise InferenceError(f"Unexpected feature matrix shape: {matrix.shape}")
            outputs = self._session.run(None, {self._input_name: matrix})
            logits = np.asarray(outputs[0], dtype=np.float64).reshape(-1)
            if logits.shape[0] != len(records):
                raise InferenceError("ONNX output batch size mismatch")
            probabilities = _sigmoid(logits)
            predictions = (probabilities >= self.threshold).astype(int)
            return PredictionResult(
                probabilities=probabilities,
                predictions=predictions,
            )
        except (ModelNotReadyError, InferenceError):
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Inference failed")
            raise InferenceError("Inference failed") from exc

    def info(self) -> dict[str, Any]:
        return {
            "model_name": self.settings.model_name,
            "model_version": self.model_version,
            "backend": self.backend,
            "model_format": "onnx-fp32",
            "input_features_count": int(self._input_dim or 0),
            "threshold": self.threshold,
            "max_batch_size": int(self.settings.max_batch_size),
            "ready": self._ready,
        }
