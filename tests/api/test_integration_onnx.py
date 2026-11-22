"""Integration: API response vs direct ONNX runtime on real artifacts."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import dependencies
from src.api.inference import OnnxInferenceRuntime
from src.api.main import app
from src.api.settings import Settings, get_settings
from src.config import nn_onnx_path, preprocessor_path
from tests.api.conftest import sample_client_payload


@pytest.fixture
def real_api_client(monkeypatch):
    if not nn_onnx_path().is_file() or not preprocessor_path().is_file():
        pytest.skip("Stage 1 artifacts not available")
    get_settings.cache_clear()
    settings = Settings(
        MODEL_PATH=str(nn_onnx_path()),
        PREPROCESSOR_PATH=str(preprocessor_path()),
        MODEL_VERSION="mlp-onnx-fp32-v1",
        EXPECTED_INPUT_DIM=47,
        PREDICTION_THRESHOLD=0.5,
    )
    runtime = OnnxInferenceRuntime(settings)
    runtime.load()

    def _init(_settings=None):
        dependencies._runtime = runtime
        return runtime

    monkeypatch.setattr(dependencies, "init_runtime", _init)
    dependencies._runtime = runtime
    with TestClient(app) as client:
        yield client, runtime
    dependencies._runtime = None
    get_settings.cache_clear()


@pytest.mark.integration
def test_api_matches_direct_onnx(real_api_client):
    client, runtime = real_api_client
    payload = sample_client_payload()
    direct = runtime.predict_records([payload])
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["prediction"] == int(direct.predictions[0])
    assert abs(body["probability_default"] - float(direct.probabilities[0])) < 1e-6


@pytest.mark.integration
def test_api_batch_matches_direct_onnx_order(real_api_client):
    client, runtime = real_api_client
    items = [
        sample_client_payload(AGE=24, LIMIT_BAL=20000),
        sample_client_payload(AGE=45, LIMIT_BAL=120000),
        sample_client_payload(AGE=33, LIMIT_BAL=50000),
    ]
    direct = runtime.predict_records(items)
    response = client.post("/predict/batch", json={"items": items})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 3
    for index, row in enumerate(results):
        assert row["prediction"] == int(direct.predictions[index])
        assert (
            abs(row["probability_default"] - float(direct.probabilities[index])) < 1e-6
        )
