"""GPU benchmark must refuse silent CPU fallback when CUDA is unavailable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.nn import benchmark as bench_mod


def test_benchmark_gpu_blocked_without_cuda(tmp_path, monkeypatch):
    monkeypatch.setattr(bench_mod.torch.cuda, "is_available", lambda: False)
    import sys
    import types

    fake = types.ModuleType("onnxruntime")
    fake.get_available_providers = lambda: ["CPUExecutionProvider"]
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)

    out = tmp_path / "gpu.json"
    report = bench_mod.benchmark_gpu(output_path=out)
    assert report["status"] == "BLOCKED_NO_GPU"
    assert report["torch_cuda_is_available"] is False
    assert report.get("cuda_execution_provider_present") is False
    assert "results" not in report or not report.get("results")
    assert out.is_file()
    disk = json.loads(out.read_text(encoding="utf-8"))
    assert disk["status"] == "BLOCKED_NO_GPU"
    assert not disk.get("results")


def test_benchmark_gpu_rejects_cpu_fallback_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(bench_mod.torch.cuda, "is_available", lambda: False)
    import sys
    import types

    fake = types.ModuleType("onnxruntime")
    fake.get_available_providers = lambda: ["CPUExecutionProvider"]
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)

    with pytest.raises(RuntimeError, match="refuses CPU fallback"):
        bench_mod.benchmark_gpu(
            output_path=tmp_path / "x.json", allow_cpu_fallback=True
        )


def test_tracked_gpu_status_evidence_schema():
    path = Path("results/block7/gpu_status.json")
    assert path.is_file(), "Git-tracked GPU evidence missing"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "VERIFIED_GPU"
    assert data["hardened_colab"]["status"] == "VERIFIED_GPU"
    assert data["local_laptop"]["status"] == "BLOCKED_NO_GPU"
    assert data["quantized_gpu"] == "NOT_EXECUTED"
    assert data.get("results") in (None, [], {})


def test_tracked_parity_and_quality_evidence_present():
    root = Path("results/block7")
    for name in (
        "parity_summary.json",
        "quality_fp32_vs_quant.json",
        "cpu_benchmark_model_only.csv",
        "api_load_summary.json",
        "run_metadata.json",
    ):
        assert (root / name).is_file(), name
    parity = json.loads((root / "parity_summary.json").read_text(encoding="utf-8"))
    assert parity["result"] == "PASS"
    quality = json.loads(
        (root / "quality_fp32_vs_quant.json").read_text(encoding="utf-8")
    )
    assert "metric_deltas" in quality
    assert "confusion_fp32" in quality
