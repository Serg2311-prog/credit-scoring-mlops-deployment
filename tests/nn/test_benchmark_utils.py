"""Unit tests for Block 7 benchmark helpers (no heavy benches)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.nn.benchmark import _percentile, _summarize_timed, _time_callable
from src.nn.parity import compare_batches


def test_percentile_and_timing_helpers():
    samples = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert _percentile(samples, 50) == 3.0
    assert _percentile(samples, 99) >= 4.0

    calls = {"n": 0}

    def fn() -> None:
        calls["n"] += 1

    stats = _time_callable(fn, warmup=2, timed=5)
    assert stats["n_warmup"] == 2
    assert stats["n_timed"] == 5
    assert "latency_p99_ms" in stats
    assert "cold_start_ms" in stats
    assert calls["n"] == 1 + 2 + 5  # cold + warmup + timed

    summary = _summarize_timed(
        [
            {
                "latency_p50_ms": 1.0,
                "latency_p95_ms": 2.0,
                "latency_p99_ms": 3.0,
                "latency_mean_ms": 1.5,
                "cold_start_ms": 10.0,
                "throughput_samples_per_s": 100.0,
            }
        ]
    )
    assert summary["latency_p99_ms_mean_over_repeats"] == 3.0


def test_compare_batches_agreement_fields():
    a = np.array([0.1, 0.2, 0.9], dtype=np.float64)
    b = np.array([0.1, 0.21, 0.9], dtype=np.float64)
    stats = compare_batches(a, b)
    assert stats["n"] == 3
    assert stats["max_abs"] >= stats["mae"]


def test_existing_gpu_artifact_schema_if_present():
    path = Path("artifacts/benchmark_gpu.json")
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "status" in data
    assert data["status"] in {"SKIPPED", "BLOCKED_NO_GPU", "completed"}
    if data["status"] == "completed":
        assert "results" in data
    else:
        # Must not invent GPU latency tables when blocked/skipped
        assert "results" not in data or not data.get("results")
