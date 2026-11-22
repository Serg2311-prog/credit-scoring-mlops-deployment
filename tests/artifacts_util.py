"""Helpers to classify local ONNX/preprocessor artifacts for tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.config import nn_onnx_path, preprocessor_path

MARKER = "CI_SYNTHETIC_ARTIFACTS.json"
PROD_VERSION = "mlp-onnx-fp32-v1"
PROD_INPUT_DIM = 47


@dataclass(frozen=True)
class ArtifactBundle:
    model_path: Path
    preprocessor_path: Path
    model_version: str
    expected_input_dim: int
    synthetic: bool


def discover_artifacts() -> ArtifactBundle | None:
    model = nn_onnx_path()
    prep = preprocessor_path()
    if not model.is_file() or not prep.is_file():
        return None
    marker = model.parent / MARKER
    if marker.is_file():
        payload = json.loads(marker.read_text(encoding="utf-8"))
        return ArtifactBundle(
            model_path=model,
            preprocessor_path=prep,
            model_version=str(payload.get("model_version", "ci-synthetic-mlp-v1")),
            expected_input_dim=int(payload["input_dim"]),
            synthetic=True,
        )
    return ArtifactBundle(
        model_path=model,
        preprocessor_path=prep,
        model_version=PROD_VERSION,
        expected_input_dim=PROD_INPUT_DIM,
        synthetic=False,
    )
