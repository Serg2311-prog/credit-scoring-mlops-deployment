"""Integration: API response vs direct ONNX runtime.

Uses local artifacts under models/:
- CI-synthetic (marker present) → contract tests
- Stage-1 production (no marker) → real artifact tests
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import dependencies
from src.api.inference import OnnxInferenceRuntime
from src.api.main import app
from src.api.settings import Settings, get_settings
from tests.api.conftest import sample_client_payload
from tests.artifacts_util import discover_artifacts


@pytest.fixture
def artifact_api_client(monkeypatch):
    bundle = discover_artifacts()
    if bundle is None:
        pytest.skip("ONNX/preprocessor artifacts not available")
    get_settings.cache_clear()
    settings = Settings(
        MODEL_PATH=str(bundle.model_path),
        PREPROCESSOR_PATH=str(bundle.preprocessor_path),
        MODEL_VERSION=bundle.model_version,
        EXPECTED_INPUT_DIM=bundle.expected_input_dim,
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
        yield client, runtime, bundle
    dependencies._runtime = None
    get_settings.cache_clear()


@pytest.mark.integration
def test_api_matches_direct_onnx(artifact_api_client):
    client, runtime, _bundle = artifact_api_client
    payload = sample_client_payload()
    direct = runtime.predict_records([payload])
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["prediction"] == int(direct.predictions[0])
    assert abs(body["probability_default"] - float(direct.probabilities[0])) < 1e-6


@pytest.mark.integration
def test_api_batch_matches_direct_onnx_order(artifact_api_client):
    client, runtime, _bundle = artifact_api_client
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


@pytest.mark.real_artifacts
def test_production_artifact_metadata(artifact_api_client):
    _client, runtime, bundle = artifact_api_client
    if bundle.synthetic:
        pytest.skip("Production artifacts not present (CI synthetic in use)")
    assert bundle.model_version == "mlp-onnx-fp32-v1"
    assert runtime.input_dim == 47
