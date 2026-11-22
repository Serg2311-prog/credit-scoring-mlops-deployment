from pathlib import Path

import pytest

from src.api.errors import ModelNotReadyError
from src.api.inference import OnnxInferenceRuntime
from src.api.settings import Settings
from src.config import nn_onnx_path, preprocessor_path
from tests.api.conftest import sample_client_payload


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
def test_real_onnx_runtime_predicts():
    if not nn_onnx_path().is_file() or not preprocessor_path().is_file():
        pytest.skip("Stage 1 artifacts not available")
    settings = Settings(
        MODEL_PATH=str(nn_onnx_path()),
        PREPROCESSOR_PATH=str(preprocessor_path()),
        EXPECTED_INPUT_DIM=47,
    )
    runtime = OnnxInferenceRuntime(settings)
    runtime.load()
    assert runtime.ready is True
    assert runtime.input_dim == 47
    result = runtime.predict_records([sample_client_payload()])
    assert result.probabilities.shape == (1,)
    assert 0.0 <= float(result.probabilities[0]) <= 1.0
    assert int(result.predictions[0]) in (0, 1)


def test_fake_runtime_inference_error(api_client, fake_runtime):
    fake_runtime.fail_inference = True
    response = api_client.post("/predict", json=sample_client_payload())
    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "inference_error"
    assert "Traceback" not in body["message"]
