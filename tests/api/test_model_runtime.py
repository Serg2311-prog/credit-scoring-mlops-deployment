from pathlib import Path

import pytest

from src.api.errors import ModelNotReadyError
from src.api.inference import OnnxInferenceRuntime
from src.api.settings import Settings
from tests.api.conftest import sample_client_payload
from tests.artifacts_util import discover_artifacts


def test_runtime_missing_artifacts(tmp_path: Path):
    settings = Settings(
        MODEL_PATH=str(tmp_path / "missing.onnx"),
        PREPROCESSOR_PATH=str(tmp_path / "missing.joblib"),
    )
    runtime = OnnxInferenceRuntime(settings)
    with pytest.raises(FileNotFoundError):
        runtime.load()
    assert runtime.ready is False


def test_runtime_not_ready_blocks_predict(tmp_path: Path):
    settings = Settings(
        MODEL_PATH=str(tmp_path / "missing.onnx"),
        PREPROCESSOR_PATH=str(tmp_path / "missing.joblib"),
    )
    runtime = OnnxInferenceRuntime(settings)
    with pytest.raises(ModelNotReadyError):
        runtime.predict_records([sample_client_payload()])


@pytest.mark.integration
def test_onnx_runtime_predicts_with_available_artifacts():
    bundle = discover_artifacts()
    if bundle is None:
        pytest.skip("ONNX/preprocessor artifacts not available")
    settings = Settings(
        MODEL_PATH=str(bundle.model_path),
        PREPROCESSOR_PATH=str(bundle.preprocessor_path),
        EXPECTED_INPUT_DIM=bundle.expected_input_dim,
        MODEL_VERSION=bundle.model_version,
    )
    runtime = OnnxInferenceRuntime(settings)
    runtime.load()
    assert runtime.ready is True
    assert runtime.input_dim == bundle.expected_input_dim
    result = runtime.predict_records([sample_client_payload()])
    assert result.probabilities.shape == (1,)
    assert 0.0 <= float(result.probabilities[0]) <= 1.0
    assert int(result.predictions[0]) in (0, 1)


@pytest.mark.real_artifacts
def test_production_onnx_has_dim_47():
    bundle = discover_artifacts()
    if bundle is None:
        pytest.skip("Artifacts not available")
    if bundle.synthetic:
        pytest.skip("Production artifacts not present (CI synthetic in use)")
    assert bundle.expected_input_dim == 47
    settings = Settings(
        MODEL_PATH=str(bundle.model_path),
        PREPROCESSOR_PATH=str(bundle.preprocessor_path),
        EXPECTED_INPUT_DIM=47,
        MODEL_VERSION="mlp-onnx-fp32-v1",
    )
    runtime = OnnxInferenceRuntime(settings)
    runtime.load()
    assert runtime.input_dim == 47


def test_fake_runtime_inference_error(api_client, fake_runtime):
    fake_runtime.fail_inference = True
    response = api_client.post("/predict", json=sample_client_payload())
    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "inference_error"
    assert "Traceback" not in body["message"]
