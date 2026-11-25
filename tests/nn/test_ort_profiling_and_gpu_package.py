"""Block 7 GPU evidence integrity (CI-safe) + packaging helpers.

Evidence integrity MUST NOT require production models/ weights (absent on
GitHub-hosted runners after synthetic artifact generation).
Production binding lives in test_gpu_evidence_production_binding.py
(@pytest.mark.real_artifacts).
"""

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
from tests.nn.gpu_evidence_constants import (
    EXPECTED_ONNX_FP32_SHA256,
    EXPECTED_PT_SHA256,
    EXPECTED_SYNTHETIC_FEATURES_SHA256,
    HARDENED_DIR,
    HISTORICAL_DIR,
)

PROFILE = Path(f"{HISTORICAL_DIR}/onnxruntime_profile__2026-11-24_15-19-30_623.json")
EVIDENCE_JSON = Path(f"{HISTORICAL_DIR}/colab_gpu_benchmark.json")
EVIDENCE_CSV = Path(f"{HISTORICAL_DIR}/colab_gpu_benchmark.csv")
HARDENED_JSON = Path(f"{HARDENED_DIR}/colab_gpu_benchmark.json")
HARDENED_CSV = Path(f"{HARDENED_DIR}/colab_gpu_benchmark.csv")
HARDENED_PROFILE = Path(
    f"{HARDENED_DIR}/onnxruntime_profile__2026-11-24_15-38-33_414.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_json_csv_consistent(report: dict, csv_path: Path) -> None:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    assert len(report["results"]) == 30
    assert len(rows) == 30
    keys = {
        (row["variant"], row["mode"], int(row["batch_size"]))
        for row in report["results"]
    }
    assert len(keys) == 30
    for item in report["results"]:
        key = (item["variant"], item["mode"], int(item["batch_size"]))
        match = next(
            row
            for row in rows
            if (row["variant"], row["mode"], int(row["batch_size"])) == key
        )
        assert (
            abs(
                float(item["latency_p50_ms_mean_over_repeats"])
                - float(match["latency_p50_ms_mean_over_repeats"])
            )
            < 1e-9
        )


def _assert_manifest_files(manifest_path: Path, root: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "files" in manifest
    for rel, meta in manifest["files"].items():
        path = root / rel
        assert path.is_file(), rel
        assert _sha256(path) == meta["sha256"], (
            f"{rel}: working-tree SHA256 != manifest. "
            "Evidence files are marked -text in .gitattributes; "
            "EOL conversion would break byte integrity."
        )


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


def test_historical_evidence_json_csv_consistency():
    report = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    assert report["parity_status"] == "PASS"
    _assert_json_csv_consistent(report, EVIDENCE_CSV)


def test_sha256sums_manifest_integrity_historical():
    _assert_manifest_files(
        Path(f"{HISTORICAL_DIR}/SHA256SUMS.json"), Path(HISTORICAL_DIR)
    )


def test_sha256sums_manifest_integrity_hardened():
    _assert_manifest_files(Path(f"{HARDENED_DIR}/SHA256SUMS.json"), Path(HARDENED_DIR))


def test_evidence_model_hashes_cross_consistent_without_models_dir():
    """CI-safe: compare declared hashes across evidence, not models/ bytes."""
    historical = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    hardened = json.loads(HARDENED_JSON.read_text(encoding="utf-8"))
    hist_onnx = historical["models"]["onnx_fp32"]["sha256"]
    hist_pt = historical["models"]["pytorch_checkpoint"]["sha256"]
    hard_onnx = hardened["models"]["onnx_fp32"]["sha256"]
    hard_pt = hardened["models"]["pytorch_checkpoint"]["sha256"]
    assert hist_onnx == hard_onnx == EXPECTED_ONNX_FP32_SHA256
    assert hist_pt == hard_pt == EXPECTED_PT_SHA256
    assert (
        historical["inputs"]["sha256"]
        == hardened["inputs"]["sha256"]
        == EXPECTED_SYNTHETIC_FEATURES_SHA256
    )


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


def test_hardened_evidence_integrity_without_models_dir():
    report = json.loads(HARDENED_JSON.read_text(encoding="utf-8"))
    assert report["gpu_status"] == "VERIFIED_GPU"
    assert report["parity_status"] == "PASS"
    assert report.get("quality_evaluation") is False
    assert report.get("runner_generation") == "hardened_block73"
    _assert_json_csv_consistent(report, HARDENED_CSV)
    # 9000 timed measurements: 30 configs * 100 timed * 3 repeats
    assert all(int(r["timed_runs"]) == 100 for r in report["results"])
    assert all(int(r["repeats"]) == 3 for r in report["results"])
    assert len(report["results"]) * 100 * 3 == 9000

    analysis = analyze_ort_node_providers(load_ort_profile(HARDENED_PROFILE))
    assert analysis["status"] == "PASS"
    assert analysis["cuda_node_events"] == 8
    assert analysis["cpu_node_events"] == 0

    manifest = json.loads(
        Path(f"{HARDENED_DIR}/SHA256SUMS.json").read_text(encoding="utf-8")
    )
    assert manifest["gpu_status"] == "VERIFIED_GPU"
    runner = Path(f"{HARDENED_DIR}/runner_used/run_benchmark.py")
    assert runner.is_file()
    assert _sha256(runner) == manifest["runner_sha256"]
    assert _sha256(runner) == _sha256(Path("scripts/gpu_benchmark/run_benchmark.py"))

    gpu_doc = Path("docs/gpu_benchmark_colab.md").read_text(encoding="utf-8")
    assert "NOT_REVERIFIED" not in gpu_doc
    assert "VERIFIED_GPU" in gpu_doc
    assert "results/block7/colab/hardened" in gpu_doc


def test_evidence_integrity_does_not_require_production_pt():
    """Regression: integrity uses evidence JSON digests, not models/*.pt I/O."""
    import ast

    historical = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    assert historical["models"]["pytorch_checkpoint"]["sha256"] == EXPECTED_PT_SHA256
    binding = Path("tests/nn/test_gpu_evidence_production_binding.py").read_text(
        encoding="utf-8"
    )
    assert "pytest.mark.real_artifacts" in binding
    assert "credit_scoring_nn.pt" in binding
    tree = ast.parse(
        Path("tests/nn/test_ort_profiling_and_gpu_package.py").read_text(
            encoding="utf-8"
        )
    )
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "test_evidence_integrity_does_not_require_production_pt"
        ):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                assert "credit_scoring_nn.pt" not in child.value


def test_tampered_evidence_file_breaks_manifest(tmp_path):
    root = Path(HARDENED_DIR)
    manifest = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    rel = "colab_gpu_benchmark.csv"
    original = (root / rel).read_bytes()
    fake = tmp_path / "tampered.csv"
    fake.write_bytes(original + b"\n#tamper")
    assert (
        hashlib.sha256(fake.read_bytes()).hexdigest()
        != manifest["files"][rel]["sha256"]
    )


def test_gitattributes_marks_colab_evidence_as_binary():
    text = Path(".gitattributes").read_text(encoding="utf-8")
    assert "results/block7/colab/** -text" in text


def test_csv_bytes_match_original_colab_zip_when_present():
    zip_path = Path("artifacts/block7/gpu_benchmark_hardened_evidence.zip")
    if not zip_path.is_file():
        zip_path = Path.home() / "Downloads" / "gpu_benchmark_hardened_evidence.zip"
    if not zip_path.is_file():
        pytest.skip("original hardened evidence ZIP not available locally")
    with zipfile.ZipFile(zip_path) as zf:
        zbytes = zf.read("out/colab_gpu_benchmark.csv")
    assert HARDENED_CSV.read_bytes() == zbytes
    assert _sha256(HARDENED_CSV) == hashlib.sha256(zbytes).hexdigest()
