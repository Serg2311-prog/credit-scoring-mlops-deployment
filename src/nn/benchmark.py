"""CPU/GPU benchmarks: PyTorch vs ONNX vs quantized ONNX."""

from __future__ import annotations

import argparse
import time
from typing import Any, Callable

import numpy as np
import pandas as pd
import psutil
import torch

from src.config import (
    artifacts_dir,
    dump_json,
    load_params,
    nn_onnx_path,
    nn_quant_onnx_path,
    processed_dir,
)
from src.models.evaluate import compute_metrics
from src.models.preprocessing import load_preprocessor, transform_features
from src.nn.runtime import (
    configure_cpu_threads,
    load_checkpoint,
    probabilities_from_logits,
)
from src.schema import detect_target


def _rss_mb() -> float:
    return psutil.Process().memory_info().rss / (1024 * 1024)


def _percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def _time_callable(
    fn: Callable[[], None],
    warmup: int,
    timed: int,
) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(timed):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    return {
        "latency_p50_ms": _percentile(samples, 50),
        "latency_p95_ms": _percentile(samples, 95),
        "latency_mean_ms": float(np.mean(samples)),
        "latency_std_ms": float(np.std(samples)),
        "n_timed": float(timed),
        "n_warmup": float(warmup),
    }


def _load_raw_and_features() -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    params = load_params()
    test_path = processed_dir() / "test.csv"
    if not test_path.is_file():
        raise FileNotFoundError("Нет test.csv для benchmark")
    test_df = pd.read_csv(test_path)
    target = detect_target(
        test_df.columns, preferred=params["prepare"]["target_column"]
    )
    y_true = test_df[target].astype(int).to_numpy()
    raw_features = test_df.drop(columns=[target])
    features = transform_features(load_preprocessor(), raw_features)
    return raw_features, features, y_true


def _summarize_timed(repeat_stats: list[dict[str, float]]) -> dict[str, float]:
    latency_p50 = float(np.mean([item["latency_p50_ms"] for item in repeat_stats]))
    latency_p95 = float(np.mean([item["latency_p95_ms"] for item in repeat_stats]))
    throughput = float(
        np.mean([item["throughput_samples_per_s"] for item in repeat_stats])
    )
    return {
        "latency_p50_ms_mean_over_repeats": latency_p50,
        "latency_p95_ms_mean_over_repeats": latency_p95,
        "throughput_samples_per_s_mean_over_repeats": throughput,
    }


def _e2e_torch_runner(
    model: torch.nn.Module,
    preprocessor,
    raw_batch: pd.DataFrame,
    device: torch.device,
) -> Callable[[], None]:
    def _run() -> None:
        matrix = transform_features(preprocessor, raw_batch)
        tensor = torch.from_numpy(matrix.astype(np.float32)).to(device)
        with torch.no_grad():
            _ = model(tensor)
        if device.type == "cuda":
            torch.cuda.synchronize()

    return _run


def _e2e_ort_runner(
    session, preprocessor, raw_batch: pd.DataFrame
) -> Callable[[], None]:
    input_name = session.get_inputs()[0].name

    def _run() -> None:
        matrix = transform_features(preprocessor, raw_batch).astype(np.float32)
        _ = session.run(None, {input_name: matrix})

    return _run


def _torch_runner(
    model: torch.nn.Module,
    batch: np.ndarray,
    device: torch.device,
) -> Callable[[], None]:
    tensor = torch.from_numpy(batch.astype(np.float32)).to(device)

    def _run() -> None:
        with torch.no_grad():
            _ = model(tensor)
        if device.type == "cuda":
            torch.cuda.synchronize()

    return _run


def _ort_runner(session, batch: np.ndarray) -> Callable[[], None]:
    input_name = session.get_inputs()[0].name
    feed = {input_name: batch.astype(np.float32)}

    def _run() -> None:
        _ = session.run(None, feed)

    return _run


def _predict_torch(model, features: np.ndarray, device: torch.device) -> np.ndarray:
    model.eval()
    outputs: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(features), 1024):
            batch = torch.from_numpy(
                features[start : start + 1024].astype(np.float32)
            ).to(device)
            logits = model(batch)
            outputs.append(probabilities_from_logits(logits))
    return np.concatenate(outputs)


def _predict_ort(session, features: np.ndarray) -> np.ndarray:
    input_name = session.get_inputs()[0].name
    outputs: list[np.ndarray] = []
    for start in range(0, len(features), 1024):
        batch = features[start : start + 1024].astype(np.float32)
        logits = session.run(None, {input_name: batch})[0]
        outputs.append(probabilities_from_logits(np.asarray(logits).reshape(-1)))
    return np.concatenate(outputs)


def benchmark_cpu() -> dict[str, Any]:
    import onnxruntime as ort

    configure_cpu_threads()
    params = load_params()
    bench = params.get("benchmark", {})
    warmup = int(bench.get("warmup_runs", 20))
    timed = int(bench.get("timed_runs", 100))
    repeats = int(bench.get("repeats", 3))
    batch_sizes = [int(item) for item in bench.get("batch_sizes", [1, 16, 64, 256])]
    threshold = float(params["nn"].get("threshold", 0.5))

    raw_features, features, y_true = _load_raw_and_features()
    preprocessor = load_preprocessor()
    model, _payload = load_checkpoint(map_location="cpu")
    model.eval()
    device = torch.device("cpu")

    fp32_path = nn_onnx_path()
    quant_path = nn_quant_onnx_path()
    if not fp32_path.is_file():
        raise FileNotFoundError(f"Нет ONNX: {fp32_path}")
    if not quant_path.is_file():
        raise FileNotFoundError(f"Нет quantized ONNX: {quant_path}")

    ort_fp32 = ort.InferenceSession(str(fp32_path), providers=["CPUExecutionProvider"])
    ort_quant = ort.InferenceSession(
        str(quant_path), providers=["CPUExecutionProvider"]
    )

    variants = {
        "pytorch_cpu": {
            "kind": "torch",
            "model": model,
            "path": None,
            "size_bytes": None,
        },
        "onnx_fp32_cpu": {
            "kind": "ort",
            "session": ort_fp32,
            "path": fp32_path,
            "size_bytes": fp32_path.stat().st_size,
        },
        "onnx_quant_cpu": {
            "kind": "ort",
            "session": ort_quant,
            "path": quant_path,
            "size_bytes": quant_path.stat().st_size,
        },
    }

    # Quality on full prepared test matrix (same features for all backends)
    quality = {}
    torch_prob = _predict_torch(model, features, device)
    quality["pytorch_cpu"] = compute_metrics(y_true, torch_prob, threshold=threshold)
    quality["onnx_fp32_cpu"] = compute_metrics(
        y_true, _predict_ort(ort_fp32, features), threshold=threshold
    )
    quality["onnx_quant_cpu"] = compute_metrics(
        y_true, _predict_ort(ort_quant, features), threshold=threshold
    )

    model_only_rows: list[dict[str, Any]] = []
    e2e_rows: list[dict[str, Any]] = []
    for variant_name, variant in variants.items():
        for batch_size in batch_sizes:
            actual_bs = int(min(batch_size, len(features)))
            model_batch = features[:actual_bs]
            raw_batch = raw_features.iloc[:actual_bs].copy()

            # --- model-only: только тензорный forward ---
            model_repeat_stats = []
            rss_before = _rss_mb()
            for repeat_idx in range(repeats):
                if variant["kind"] == "torch":
                    runner = _torch_runner(variant["model"], model_batch, device)
                else:
                    runner = _ort_runner(variant["session"], model_batch)
                stats = _time_callable(runner, warmup=warmup, timed=timed)
                stats["repeat"] = repeat_idx + 1
                stats["throughput_samples_per_s"] = (
                    actual_bs / (stats["latency_mean_ms"] / 1000.0)
                    if stats["latency_mean_ms"] > 0
                    else float("nan")
                )
                model_repeat_stats.append(stats)
            rss_after = _rss_mb()
            model_summary = _summarize_timed(model_repeat_stats)
            model_only_rows.append(
                {
                    "scope": "model_only",
                    "variant": variant_name,
                    "batch_size": actual_bs,
                    "model_size_bytes": variant["size_bytes"],
                    **model_summary,
                    "rss_mb_before": rss_before,
                    "rss_mb_after": rss_after,
                    "rss_mb_delta": rss_after - rss_before,
                    "repeats": model_repeat_stats,
                    "quality_metrics": quality[variant_name],
                }
            )
            print(
                f"[model_only] {variant_name} batch={actual_bs}: "
                f"p50={model_summary['latency_p50_ms_mean_over_repeats']:.3f}ms "
                f"p95={model_summary['latency_p95_ms_mean_over_repeats']:.3f}ms "
                f"tps={model_summary['throughput_samples_per_s_mean_over_repeats']:.1f}"
            )

            # --- end-to-end: raw DataFrame -> preprocessor -> model ---
            e2e_repeat_stats = []
            for repeat_idx in range(repeats):
                if variant["kind"] == "torch":
                    runner = _e2e_torch_runner(
                        variant["model"], preprocessor, raw_batch, device
                    )
                else:
                    runner = _e2e_ort_runner(
                        variant["session"], preprocessor, raw_batch
                    )
                stats = _time_callable(runner, warmup=warmup, timed=timed)
                stats["repeat"] = repeat_idx + 1
                stats["throughput_samples_per_s"] = (
                    actual_bs / (stats["latency_mean_ms"] / 1000.0)
                    if stats["latency_mean_ms"] > 0
                    else float("nan")
                )
                e2e_repeat_stats.append(stats)
            e2e_summary = _summarize_timed(e2e_repeat_stats)
            e2e_rows.append(
                {
                    "scope": "end_to_end",
                    "variant": variant_name,
                    "batch_size": actual_bs,
                    "model_size_bytes": variant["size_bytes"],
                    **e2e_summary,
                    "repeats": e2e_repeat_stats,
                    "quality_metrics": quality[variant_name],
                }
            )
            print(
                f"[end_to_end] {variant_name} batch={actual_bs}: "
                f"p50={e2e_summary['latency_p50_ms_mean_over_repeats']:.3f}ms "
                f"p95={e2e_summary['latency_p95_ms_mean_over_repeats']:.3f}ms "
                f"tps={e2e_summary['throughput_samples_per_s_mean_over_repeats']:.1f}"
            )

    from src.config import nn_checkpoint_path

    ckpt = nn_checkpoint_path()
    report = {
        "device": "cpu",
        "methodology": {
            "warmup_runs": warmup,
            "timed_runs": timed,
            "repeats": repeats,
            "batch_sizes": batch_sizes,
            "latency_unit": "milliseconds per batch",
            "throughput_unit": "samples/second ≈ batch_size / mean_latency_s",
            "scopes": {
                "model_only": (
                    "Только forward по заранее подготовленной float32-матрице "
                    "(без pandas/FE/preprocessor)."
                ),
                "end_to_end": (
                    "raw DataFrame batch -> preprocessor.joblib "
                    "(FeatureEngineer+ColumnTransformer) -> model forward."
                ),
            },
            "same_inputs": (
                "Одинаковые raw/test строки и одинаковые batch sizes "
                "для всех backend и обоих scopes."
            ),
            "memory": "psutil RSS процесса до/после серии model-only замеров",
            "threads": configure_cpu_threads(),
        },
        "model_sizes_bytes": {
            "pytorch_checkpoint": ckpt.stat().st_size if ckpt.is_file() else None,
            "onnx_fp32": fp32_path.stat().st_size,
            "onnx_quant": quant_path.stat().st_size,
        },
        "quality": quality,
        "results_model_only": model_only_rows,
        "results_end_to_end": e2e_rows,
        # backward-compatible alias
        "results": model_only_rows,
        "status": "completed",
    }
    dump_json(artifacts_dir() / "benchmark_cpu.json", report)
    print(f"Отчёт: {artifacts_dir() / 'benchmark_cpu.json'}")
    return report


def benchmark_gpu() -> dict[str, Any]:
    """Отдельный GPU-сценарий. Без CUDA возвращает SKIPPED."""
    configure_cpu_threads()
    if not torch.cuda.is_available():
        report = {
            "device": "cuda",
            "status": "SKIPPED",
            "reason": "GPU/CUDA недоступна на этой машине",
        }
        dump_json(artifacts_dir() / "benchmark_gpu.json", report)
        print("GPU benchmark: SKIPPED (CUDA unavailable)")
        return report

    params = load_params()
    bench = params.get("benchmark", {})
    warmup = int(bench.get("warmup_runs", 20))
    timed = int(bench.get("timed_runs", 100))
    repeats = int(bench.get("repeats", 3))
    batch_sizes = [int(item) for item in bench.get("batch_sizes", [1, 16, 64, 256])]

    _raw_features, features, _y_true = _load_raw_and_features()
    model, _payload = load_checkpoint(map_location="cpu")
    device = torch.device("cuda")
    model = model.to(device)
    model.eval()

    rows = []
    for batch_size in batch_sizes:
        batch = features[: min(batch_size, len(features))]
        actual_bs = int(len(batch))
        repeat_stats = []
        for repeat_idx in range(repeats):
            runner = _torch_runner(model, batch, device)
            stats = _time_callable(runner, warmup=warmup, timed=timed)
            stats["repeat"] = repeat_idx + 1
            stats["throughput_samples_per_s"] = (
                actual_bs / (stats["latency_mean_ms"] / 1000.0)
                if stats["latency_mean_ms"] > 0
                else float("nan")
            )
            repeat_stats.append(stats)
        summary = _summarize_timed(repeat_stats)
        rows.append(
            {
                "scope": "model_only",
                "variant": "pytorch_cuda",
                "batch_size": actual_bs,
                **summary,
                "repeats": repeat_stats,
            }
        )

    report = {
        "device": "cuda",
        "status": "completed",
        "cuda_device_name": torch.cuda.get_device_name(0),
        "results": rows,
    }
    dump_json(artifacts_dir() / "benchmark_gpu.json", report)
    print(f"GPU benchmark completed: {artifacts_dir() / 'benchmark_gpu.json'}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark credit scoring MLP")
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "gpu"],
        default="cpu",
        help="cpu — полный сравнительный прогон; cuda/gpu — отдельный GPU сценарий",
    )
    args = parser.parse_args()
    if args.device in {"cuda", "gpu"}:
        benchmark_gpu()
    else:
        benchmark_cpu()


if __name__ == "__main__":
    main()
