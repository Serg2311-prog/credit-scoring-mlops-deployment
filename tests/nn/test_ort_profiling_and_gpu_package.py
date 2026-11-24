"""Block 7.3: ORT profiling, GPU rejection, ZIP paths, evidence integrity."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from src.nn.ort_profiling import (
    analyze_ort_node_providers,
    load_ort_profile,
    require_cuda_only_nodes,
)

PROFILE = Path("results/block7/colab/onnxruntime_profile__2026-11-24_15-19-30_623.json")
EVIDENCE_JSON = Path("results/block7/colab/colab_gpu_benchmark.json")
EVIDENCE_CSV = Path("results/block7/colab/colab_gpu_benchmark.csv")


def test_parse_historical_ort_profile_cuda_only():
    events = load_ort_profile(PROFILE)
    analysis = analyze_ort_node_providers(events)
    assert analysis["n_events_total"] == 12
    assert analysis["n_node_events"] == 8
    assert analysis["cuda_node_events"] == 8
    assert analysis["cpu_node_events"] == 0
    assert analysis["all_nodes_on_cuda"] is True
    assert analysis["status"] == "PASS"
    require_cuda_only_nodes(events)


def test_empty_profiling_rejected():
    with pytest.raises(RuntimeError, match="zero Node events"):
        require_cuda_only_nodes([{"cat": "Session", "args": {}}])


def test_cpu_node_events_rejected():
    events = [
        {
            "cat": "Node",
            "args": {"provider": "CPUExecutionProvider", "op_name": "Gemm"},
        }
    ]
    with pytest.raises(RuntimeError, match="CPU Node"):
        require_cuda_only_nodes(events)


def test_mixed_providers_rejected():
    events = [
        {"cat": "Node", "args": {"provider": "CUDAExecutionProvider"}},
        {"cat": "Node", "args": {"provider": "CPUExecutionProvider"}},
    ]
    analysis = analyze_ort_node_providers(events)
    assert analysis["status"] == "FAIL"
    with pytest.raises(RuntimeError):
        require_cuda_only_nodes(events)


def test_evidence_json_csv_consistency():
    report = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(EVIDENCE_CSV.open(encoding="utf-8")))
    assert len(report["results"]) == 30
    assert len(rows) == 30
    assert report["parity_status"] == "PASS"
    for item in report["results"]:
        key = (item["variant"], item["mode"], int(item["batch_size"]))
        match = next(
            r for r in rows if (r["variant"], r["mode"], int(r["batch_size"])) == key
        )
        assert (
            abs(
                float(item["latency_p50_ms_mean_over_repeats"])
                - float(match["latency_p50_ms_mean_over_repeats"])
            )
            < 1e-9
        )


def test_evidence_model_sha256_matches_production():
    report = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    onnx = hashlib.sha256(
        Path("models/credit_scoring_nn.onnx").read_bytes()
    ).hexdigest()
    pt = hashlib.sha256(Path("models/credit_scoring_nn.pt").read_bytes()).hexdigest()
    assert report["models"]["onnx_fp32"]["sha256"] == onnx
    assert report["models"]["pytorch_checkpoint"]["sha256"] == pt


def test_sha256sums_manifest_integrity():
    manifest = json.loads(
        Path("results/block7/colab/SHA256SUMS.json").read_text(encoding="utf-8")
    )
    assert manifest["model_sha256_crosscheck"]["onnx_match"] is True
    assert manifest["model_sha256_crosscheck"]["pt_match"] is True
    for rel, meta in manifest["files"].items():
        path = Path("results/block7/colab") / rel
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == meta["sha256"], rel


def test_input_validation_helper():
    import sys

    root = Path("scripts/gpu_benchmark").resolve()
    sys.path.insert(0, str(root))
    from run_benchmark import validate_features  # type: ignore

    good = np.zeros((128, 47), dtype=np.float32)
    digest = hashlib.sha256(good.tobytes()).hexdigest()
    info = validate_features(good, expected_sha256=digest, batch_sizes=[1, 8, 32])
    assert info["finite"] is True
    with pytest.raises(ValueError, match="dtype"):
        validate_features(
            good.astype(np.float64), expected_sha256=None, batch_sizes=[1]
        )
    with pytest.raises(ValueError, match="non-finite"):
        bad = good.copy()
        bad[0, 0] = np.nan
        validate_features(bad, expected_sha256=None, batch_sizes=[1])
    with pytest.raises(ValueError, match="SHA256"):
        validate_features(good, expected_sha256="deadbeef", batch_sizes=[1])


def test_zip_path_normalization_posix(tmp_path):
    import sys

    root = Path("scripts/gpu_benchmark").resolve()
    sys.path.insert(0, str(root))
    from package_zip import add_tree  # type: ignore

    src = tmp_path / "pkg"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "file.txt").write_text("x", encoding="utf-8")
    out = tmp_path / "t.zip"
    with zipfile.ZipFile(out, "w") as zf:
        names = add_tree(zf, src, "colab_gpu_benchmark")
    assert names
    assert all("\\" not in name for name in names)
    assert all(name.startswith("colab_gpu_benchmark/") for name in names)
    assert any(name.endswith("sub/file.txt") for name in names)


def test_gpu_status_doc_distinguishes_historical_vs_hardened():
    status = json.loads(
        Path("results/block7/gpu_status.json").read_text(encoding="utf-8")
    )
    assert status["status"] == "VERIFIED_GPU"
    assert status["hardened_colab"]["status"] == "VERIFIED_GPU"
    assert (
        status["historical_colab_block72"]["status"] == "VERIFIED_GPU_HISTORICAL_COLAB"
    )
    assert status["local_laptop"]["status"] == "BLOCKED_NO_GPU"
    assert status["hardened_colab"]["parity_status"] == "PASS"


def test_hardened_evidence_integrity():
    root = Path("results/block7/colab/hardened")
    report = json.loads((root / "colab_gpu_benchmark.json").read_text(encoding="utf-8"))
    rows = list(
        csv.DictReader((root / "colab_gpu_benchmark.csv").open(encoding="utf-8"))
    )
    assert report["gpu_status"] == "VERIFIED_GPU"
    assert report["parity_status"] == "PASS"
    assert report.get("quality_evaluation") is False
    assert len(report["results"]) == 30
    assert len(rows) == 30
    keys = {(r["variant"], r["mode"], int(r["batch_size"])) for r in report["results"]}
    assert len(keys) == 30
    for item in report["results"]:
        key = (item["variant"], item["mode"], int(item["batch_size"]))
        match = next(
            r for r in rows if (r["variant"], r["mode"], int(r["batch_size"])) == key
        )
        assert (
            abs(
                float(item["latency_p50_ms_mean_over_repeats"])
                - float(match["latency_p50_ms_mean_over_repeats"])
            )
            < 1e-9
        )
    onnx = hashlib.sha256(
        Path("models/credit_scoring_nn.onnx").read_bytes()
    ).hexdigest()
    pt = hashlib.sha256(Path("models/credit_scoring_nn.pt").read_bytes()).hexdigest()
    assert report["models"]["onnx_fp32"]["sha256"] == onnx
    assert report["models"]["pytorch_checkpoint"]["sha256"] == pt
    profile = root / "onnxruntime_profile__2026-11-24_15-38-33_414.json"
    analysis = analyze_ort_node_providers(load_ort_profile(profile))
    assert analysis["status"] == "PASS"
    assert analysis["cuda_node_events"] == 8
    assert analysis["cpu_node_events"] == 0
    manifest = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    assert manifest["gpu_status"] == "VERIFIED_GPU"
    assert manifest["model_sha256_crosscheck"]["onnx_match"] is True
    for rel, meta in manifest["files"].items():
        digest = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        assert digest == meta["sha256"], rel
    gpu_doc = Path("docs/gpu_benchmark_colab.md").read_text(encoding="utf-8")
    assert "NOT_REVERIFIED" not in gpu_doc
    assert "VERIFIED_GPU" in gpu_doc
    assert "results/block7/colab/hardened" in gpu_doc
