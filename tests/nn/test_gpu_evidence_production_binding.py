"""Bind GPU evidence model hashes to local production weights.

Hosted CI replaces models/ with synthetic ONNX via
`scripts/ci/generate_synthetic_artifacts.py` and does not ship
`credit_scoring_nn.pt` (gitignored). Those environments must SKIP this module.

When non-synthetic production artifacts are present locally, mismatch or a
missing required weight is a hard failure — never a silent pass.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.artifacts_util import MARKER, discover_artifacts
from tests.nn.gpu_evidence_constants import (
    EXPECTED_ONNX_FP32_SHA256,
    EXPECTED_PT_SHA256,
    HARDENED_DIR,
    HISTORICAL_DIR,
)

pytestmark = pytest.mark.real_artifacts

PT_PATH = Path("models/credit_scoring_nn.pt")
ONNX_PATH = Path("models/credit_scoring_nn.onnx")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_production_bundle():
    bundle = discover_artifacts()
    marker = Path("models") / MARKER
    if marker.is_file() or (bundle is not None and bundle.synthetic):
        pytest.skip(
            "CI synthetic artifacts in use — production PT/ONNX bytes are not "
            "available on hosted runners (models/*.pt gitignored; ONNX replaced)."
        )
    if bundle is None:
        pytest.skip(
            "Production ONNX/preprocessor not present in models/ "
            "(local optional; hosted CI never has them)."
        )
    return bundle


def test_production_onnx_matches_gpu_evidence_hashes():
    _require_production_bundle()
    digest = _sha256(ONNX_PATH)
    assert digest == EXPECTED_ONNX_FP32_SHA256
    historical = json.loads(
        Path(f"{HISTORICAL_DIR}/colab_gpu_benchmark.json").read_text(encoding="utf-8")
    )
    hardened = json.loads(
        Path(f"{HARDENED_DIR}/colab_gpu_benchmark.json").read_text(encoding="utf-8")
    )
    assert digest == historical["models"]["onnx_fp32"]["sha256"]
    assert digest == hardened["models"]["onnx_fp32"]["sha256"]


def test_production_pt_matches_gpu_evidence_hashes():
    _require_production_bundle()
    if not PT_PATH.is_file():
        pytest.fail(
            "Non-synthetic ONNX/preprocessor present but models/credit_scoring_nn.pt "
            "is missing. Local production binding requires the PyTorch checkpoint; "
            "hosted CI does not ship PT (gitignored)."
        )
    digest = _sha256(PT_PATH)
    assert digest == EXPECTED_PT_SHA256
    historical = json.loads(
        Path(f"{HISTORICAL_DIR}/colab_gpu_benchmark.json").read_text(encoding="utf-8")
    )
    hardened = json.loads(
        Path(f"{HARDENED_DIR}/colab_gpu_benchmark.json").read_text(encoding="utf-8")
    )
    assert digest == historical["models"]["pytorch_checkpoint"]["sha256"]
    assert digest == hardened["models"]["pytorch_checkpoint"]["sha256"]


def test_synthetic_onnx_is_not_accepted_as_production_evidence_hash():
    """Synthetic ONNX must not match production evidence SHA256."""
    marker = Path("models") / MARKER
    if not marker.is_file() or not ONNX_PATH.is_file():
        pytest.skip("Synthetic CI marker/ONNX not active in this environment")
    digest = _sha256(ONNX_PATH)
    assert (
        digest != EXPECTED_ONNX_FP32_SHA256
    ), "Synthetic ONNX unexpectedly matches production evidence SHA256"


def test_wrong_production_sha_would_fail_comparison():
    """Guardrail: constants used by binding tests match committed evidence JSON."""
    historical = json.loads(
        Path(f"{HISTORICAL_DIR}/colab_gpu_benchmark.json").read_text(encoding="utf-8")
    )
    assert historical["models"]["onnx_fp32"]["sha256"] == EXPECTED_ONNX_FP32_SHA256
    assert historical["models"]["pytorch_checkpoint"]["sha256"] == EXPECTED_PT_SHA256
    bogus = "0" * 64
    assert bogus != EXPECTED_ONNX_FP32_SHA256
    assert bogus != EXPECTED_PT_SHA256
