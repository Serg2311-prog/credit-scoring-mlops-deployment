"""Unit tests for kind-smoke ConfigMap patching (synthetic dim alignment)."""

from __future__ import annotations

from scripts.ci.render_kind_manifests import _patch_configmap_data


def test_patch_configmap_sets_synthetic_dim_and_version():
    docs = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "credit-scoring-api-config",
                "namespace": "credit-scoring",
            },
            "data": {
                "EXPECTED_INPUT_DIM": "47",
                "MODEL_VERSION": "mlp-onnx-fp32-v1",
                "MODEL_PATH": "/app/models/credit_scoring_nn.onnx",
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "credit-scoring-api"},
        },
    ]
    _patch_configmap_data(docs, input_dim=43, model_version="ci-synthetic-mlp-v1")
    data = docs[0]["data"]
    assert data["EXPECTED_INPUT_DIM"] == "43"
    assert data["MODEL_VERSION"] == "ci-synthetic-mlp-v1"
    assert data["MODEL_PATH"] == "/app/models/credit_scoring_nn.onnx"


def test_patch_configmap_requires_target():
    try:
        _patch_configmap_data([], input_dim=43, model_version="x")
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "not found" in str(exc)
