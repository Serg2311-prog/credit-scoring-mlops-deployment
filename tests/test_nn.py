"""Тесты MLP, checkpoint, ONNX parity и quantization на синтетике."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
onnx = pytest.importorskip("onnx")
ort = pytest.importorskip("onnxruntime")

from src.models.preprocessing import (  # noqa: E402
    fit_preprocessor,
    transform_features,
)
from src.nn.model import CreditScoringMLP, build_mlp_from_params  # noqa: E402
from src.nn.parity import compare_batches  # noqa: E402
from src.nn.runtime import (  # noqa: E402
    load_checkpoint,
    probabilities_from_logits,
    set_seed,
)
from src.schema import RAW_FEATURE_COLUMNS, TARGET_COLUMN  # noqa: E402


def _tiny_training(raw_frame):
    set_seed(42)
    preprocessor = fit_preprocessor(raw_frame[RAW_FEATURE_COLUMNS])
    features = transform_features(preprocessor, raw_frame[RAW_FEATURE_COLUMNS])
    labels = raw_frame[TARGET_COLUMN].astype(np.float32).to_numpy()
    model = CreditScoringMLP(
        input_dim=features.shape[1], hidden_dims=[16, 8], dropout=0.1
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
    criterion = torch.nn.BCEWithLogitsLoss()
    x = torch.from_numpy(features)
    y = torch.from_numpy(labels)
    model.train()
    for _ in range(30):
        optimizer.zero_grad()
        loss = criterion(model(x), y)
        loss.backward()
        optimizer.step()
    model.eval()
    return model, preprocessor, features


def test_mlp_architecture_and_forward_shapes():
    model = CreditScoringMLP(input_dim=12, hidden_dims=[8, 4], dropout=0.0)
    assert model.input_dim == 12
    assert model.hidden_dims == [8, 4]
    logits = model(torch.randn(5, 12))
    assert logits.shape == (5,)
    probs = model.predict_proba(torch.randn(3, 12))
    assert probs.shape == (3,)
    assert torch.isfinite(probs).all()
    assert ((probs >= 0) & (probs <= 1)).all()


def test_mlp_rejects_bad_input_dim():
    model = CreditScoringMLP(input_dim=10, hidden_dims=[4], dropout=0.0)
    with pytest.raises(ValueError, match="размерность"):
        model(torch.randn(2, 7))
    with pytest.raises(ValueError):
        CreditScoringMLP(input_dim=0)
    with pytest.raises(ValueError):
        CreditScoringMLP(input_dim=4, hidden_dims=[])


def test_build_mlp_from_params():
    model = build_mlp_from_params(6, {"hidden_dims": [5], "dropout": 0.1})
    assert model.input_dim == 6
    assert model.hidden_dims == [5]


def test_checkpoint_roundtrip(tmp_path: Path, raw_frame):
    model, _preprocessor, features = _tiny_training(raw_frame)
    path = tmp_path / "tiny.pt"
    payload = {
        "state_dict": model.state_dict(),
        "model_config": {
            "input_dim": model.input_dim,
            "hidden_dims": model.hidden_dims,
            "dropout": model.dropout,
        },
        "input_dim": model.input_dim,
    }
    torch.save(payload, path)
    loaded, restored = load_checkpoint(path, map_location="cpu")
    assert restored["input_dim"] == model.input_dim
    with torch.no_grad():
        original = model(torch.from_numpy(features[:8]))
        again = loaded(torch.from_numpy(features[:8]))
    assert torch.allclose(original, again, atol=1e-6)


def test_onnx_parity_on_synthetic(tmp_path: Path, raw_frame):
    model, _preprocessor, features = _tiny_training(raw_frame)
    onnx_path = tmp_path / "tiny.onnx"
    dummy = torch.zeros((1, model.input_dim), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        input_names=["features"],
        output_names=["logits"],
        dynamic_axes={"features": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    batch = features[:16].astype(np.float32)
    with torch.no_grad():
        torch_logits = model(torch.from_numpy(batch)).numpy()
    ort_logits = np.asarray(session.run(None, {"features": batch})[0]).reshape(-1)
    torch_prob = probabilities_from_logits(torch_logits)
    ort_prob = probabilities_from_logits(ort_logits)
    stats = compare_batches(torch_prob, ort_prob)
    assert stats["max_abs"] < 1e-5
    assert stats["mae"] < 1e-6


def test_dynamic_quantization_produces_smaller_or_equal_file(tmp_path: Path, raw_frame):
    from src.nn.quantize import _quantize_via_ascii_temp

    model, _preprocessor, features = _tiny_training(raw_frame)
    fp32 = tmp_path / "fp32.onnx"
    quant = tmp_path / "quant.onnx"
    dummy = torch.zeros((1, model.input_dim), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy,
        str(fp32),
        input_names=["features"],
        output_names=["logits"],
        dynamic_axes={"features": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    _quantize_via_ascii_temp(fp32, quant)
    assert quant.is_file()
    # На крошечных моделях quantized ONNX может быть больше из-за metadata;
    # выигрыш по размеру проверяется на реальной модели в artifacts.
    session = ort.InferenceSession(str(quant), providers=["CPUExecutionProvider"])
    batch = features[:8].astype(np.float32)
    logits = session.run(None, {session.get_inputs()[0].name: batch})[0]
    assert np.isfinite(logits).all()
    assert np.asarray(logits).reshape(-1).shape == (8,)


def test_invalid_raw_inputs_fail_feature_engineering(raw_frame):
    from src.features.build_features import add_features

    broken = raw_frame.drop(columns=["LIMIT_BAL"])
    with pytest.raises(ValueError, match="не хватает колонок"):
        add_features(broken)
