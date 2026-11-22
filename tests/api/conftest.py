"""Fixtures for API unit tests with mockable runtime."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api import dependencies
from src.api.inference import PredictionResult
from src.api.main import app
from src.api.settings import get_settings
from src.schema import RAW_FEATURE_COLUMNS


def sample_client_payload(**overrides):
    base = {
        "LIMIT_BAL": 20000.0,
        "SEX": 2,
        "EDUCATION": 2,
        "MARRIAGE": 1,
        "AGE": 24,
        "PAY_0": 2,
        "PAY_2": 2,
        "PAY_3": -1,
        "PAY_4": -1,
        "PAY_5": -2,
        "PAY_6": -2,
        "BILL_AMT1": 3913.0,
        "BILL_AMT2": 3102.0,
        "BILL_AMT3": 689.0,
        "BILL_AMT4": 0.0,
        "BILL_AMT5": 0.0,
        "BILL_AMT6": 0.0,
        "PAY_AMT1": 0.0,
        "PAY_AMT2": 689.0,
        "PAY_AMT3": 0.0,
        "PAY_AMT4": 0.0,
        "PAY_AMT5": 0.0,
        "PAY_AMT6": 0.0,
    }
    base.update(overrides)
    assert set(base) == set(RAW_FEATURE_COLUMNS)
    return base


@dataclass
class FakeRuntime:
    ready: bool = True
    load_error: str | None = None
    backend: str = "onnx"
    model_version: str = "mlp-onnx-fp32-v1"
    threshold: float = 0.5
    _input_dim: int = 47
    fail_inference: bool = False

    def require_ready(self) -> None:
        from src.api.errors import ModelNotReadyError

        if not self.ready:
            raise ModelNotReadyError(self.load_error or "not ready")

    def predict_records(self, records, *, request_id: str | None = None):
        from src.api.errors import InferenceError

        self.require_ready()
        if self.fail_inference:
            raise InferenceError("Inference failed")
        # Deterministic fake probabilities based on AGE for order checks.
        probs = np.array(
            [min(0.99, max(0.01, float(item["AGE"]) / 100.0)) for item in records],
            dtype=np.float64,
        )
        preds = (probs >= self.threshold).astype(int)
        versions = [self.model_version] * len(records)
        groups = ["champion"] * len(records)
        return PredictionResult(
            probabilities=probs,
            predictions=preds,
            model_versions=versions,
            ab_groups=groups,
        )

    def info(self):
        return {
            "model_name": "credit_scoring_mlp",
            "model_version": self.model_version,
            "backend": self.backend,
            "model_format": "onnx-fp32",
            "input_features_count": self._input_dim,
            "threshold": self.threshold,
            "max_batch_size": 256,
            "ready": self.ready,
        }


@pytest.fixture
def fake_runtime():
    return FakeRuntime()


@pytest.fixture
def api_client(fake_runtime, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MAX_BATCH_SIZE", "256")
    monkeypatch.setenv("MODEL_VERSION", "mlp-onnx-fp32-v1")
    get_settings.cache_clear()

    def _init(settings=None):
        dependencies._runtime = fake_runtime
        return fake_runtime

    monkeypatch.setattr(dependencies, "init_runtime", _init)
    dependencies._runtime = fake_runtime
    with TestClient(app) as client:
        yield client
    dependencies._runtime = None
    get_settings.cache_clear()


@pytest.fixture
def not_ready_client(fake_runtime, monkeypatch):
    get_settings.cache_clear()
    fake_runtime.ready = False
    fake_runtime.load_error = "missing model"

    def _init(settings=None):
        dependencies._runtime = fake_runtime
        return fake_runtime

    monkeypatch.setattr(dependencies, "init_runtime", _init)
    dependencies._runtime = fake_runtime
    with TestClient(app) as client:
        yield client
    dependencies._runtime = None
    get_settings.cache_clear()
