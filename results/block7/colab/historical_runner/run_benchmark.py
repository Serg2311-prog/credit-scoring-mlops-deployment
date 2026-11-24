#!/usr/bin/env python3
"""Self-contained CPU/GPU model-only benchmark for Colab (synthetic inputs).

Compares in one environment:
  - pytorch_cpu_fp32
  - pytorch_cuda_fp32 (model_only_on_device + with_h2d)
  - onnx_cpu_fp32
  - onnx_cuda_fp32 (model_only via IOBinding when possible; with_h2d via numpy feed)

Does NOT evaluate holdout quality. Does NOT silently fall back CUDA→CPU for
measured GPU variants.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch

from mlp_model import load_mlp_checkpoint

ROOT = Path(__file__).resolve().parent
DEFAULT_BATCHES = [1, 8, 32, 64, 128]
WARMUP = 20
TIMED = 100
REPEATS = 3
PARITY_ATOL = 1e-5
PARITY_RTOL = 1e-4


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def time_callable(
    fn: Callable[[], None],
    *,
    warmup: int,
    timed: int,
    sync: Callable[[], None] | None = None,
) -> dict[str, float]:
    for _ in range(warmup):
        fn()
        if sync:
            sync()
    samples: list[float] = []
    for _ in range(timed):
        if sync:
            sync()
        t0 = time.perf_counter()
        fn()
        if sync:
            sync()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return {
        "latency_mean_ms": float(np.mean(samples)),
        "latency_p50_ms": percentile(samples, 50),
        "latency_p95_ms": percentile(samples, 95),
        "latency_p99_ms": percentile(samples, 99),
        "latency_std_ms": float(np.std(samples)),
        "n_warmup": float(warmup),
        "n_timed": float(timed),
    }


def summarize(repeats: list[dict[str, float]]) -> dict[str, float]:
    keys = [
        "latency_mean_ms",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
    ]
    out = {f"{k}_mean_over_repeats": float(np.mean([r[k] for r in repeats])) for k in keys}
    return out


def load_features(path: Path) -> np.ndarray:
    arr = np.load(path)
    if arr.ndim != 2:
        raise ValueError("synthetic features must be 2D")
    return np.asarray(arr, dtype=np.float32)


def env_metadata() -> dict[str, Any]:
    import onnxruntime as ort

    meta: dict[str, Any] = {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "torch_cuda_is_available": bool(torch.cuda.is_available()),
        "onnxruntime": ort.__version__,
        "onnxruntime_providers": list(ort.get_available_providers()),
    }
    if torch.cuda.is_available():
        meta["cuda_device_name"] = torch.cuda.get_device_name(0)
        meta["cuda_device_count"] = torch.cuda.device_count()
        meta["cuda_runtime_version"] = getattr(torch.version, "cuda", None)
    return meta


def torch_logits(model: torch.nn.Module, batch: np.ndarray, device: torch.device) -> np.ndarray:
    tensor = torch.from_numpy(batch).to(device)
    with torch.no_grad():
        out = model(tensor)
        if device.type == "cuda":
            torch.cuda.synchronize()
        return out.detach().cpu().numpy().astype(np.float64)


def ort_session(model_path: Path, *, prefer_cuda: bool, enable_profiling: bool = False):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if enable_profiling:
        so.enable_profiling = True
    providers = list(ort.get_available_providers())
    if prefer_cuda:
        if "CUDAExecutionProvider" not in providers:
            raise RuntimeError("CUDAExecutionProvider not available")
        # Explicitly forbid CPU fallback for the measured CUDA session.
        sess = ort.InferenceSession(
            str(model_path),
            sess_options=so,
            providers=["CUDAExecutionProvider"],
        )
        used = sess.get_providers()
        if not used or used[0] != "CUDAExecutionProvider":
            raise RuntimeError(f"ORT CUDA session fell back: providers={used}")
        return sess
    sess = ort.InferenceSession(
        str(model_path),
        sess_options=so,
        providers=["CPUExecutionProvider"],
    )
    return sess


def ort_logits(sess, batch: np.ndarray) -> np.ndarray:
    inp = sess.get_inputs()[0].name
    out = sess.run(None, {inp: batch.astype(np.float32)})[0]
    return np.asarray(out, dtype=np.float64).reshape(-1)


def compare_outputs(a: np.ndarray, b: np.ndarray, name: str) -> dict[str, Any]:
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    b = np.asarray(b, dtype=np.float64).reshape(-1)
    abs_err = np.abs(a - b)
    rel = abs_err / np.maximum(np.abs(a), 1e-12)
    passed = bool(np.all(abs_err <= (PARITY_ATOL + PARITY_RTOL * np.abs(a))))
    return {
        "pair": name,
        "n": int(a.size),
        "max_abs": float(abs_err.max()),
        "mae": float(abs_err.mean()),
        "max_rel": float(rel.max()),
        "atol": PARITY_ATOL,
        "rtol": PARITY_RTOL,
        "passed": passed,
    }


def profile_ort_cuda_ops(model_path: Path, batch: np.ndarray) -> dict[str, Any]:
    """One-shot ORT CUDA profile; fails if CPU EP appears as primary provider."""
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.enable_profiling = True
    sess = ort.InferenceSession(
        str(model_path),
        sess_options=so,
        providers=["CUDAExecutionProvider"],
    )
    if sess.get_providers()[0] != "CUDAExecutionProvider":
        raise RuntimeError("profiling session not on CUDA EP")
    inp = sess.get_inputs()[0].name
    _ = sess.run(None, {inp: batch.astype(np.float32)})
    prof_path = Path(sess.end_profiling())
    text = prof_path.read_text(encoding="utf-8", errors="ignore")
    # ORT profile JSON is a list of events; count provider hints if present.
    cpu_hits = text.lower().count("cpuexecutionprovider")
    cuda_hits = text.lower().count("cudaexecutionprovider")
    # Also count "CUDA" device placements in node args when present
    return {
        "profile_file": str(prof_path.name),
        "providers": sess.get_providers(),
        "cudaexecutionprovider_mentions": cuda_hits,
        "cpuexecutionprovider_mentions": cpu_hits,
        "note": (
            "Session created with providers=['CUDAExecutionProvider'] only. "
            "CPU EP mentions in profile may include host-side bookkeeping; "
            "primary provider must remain CUDA."
        ),
        "primary_provider_ok": sess.get_providers()[0] == "CUDAExecutionProvider",
    }


def run_torch_variant(
    model: torch.nn.Module,
    features: np.ndarray,
    *,
    device: torch.device,
    mode: str,
    batch_sizes: list[int],
    warmup: int,
    timed: int,
    repeats: int,
) -> list[dict[str, Any]]:
    rows = []
    model = model.to(device)
    model.eval()
    if device.type == "cuda" and next(model.parameters()).device.type != "cuda":
        raise RuntimeError("PyTorch model not on CUDA")

    def sync() -> None:
        if device.type == "cuda":
            torch.cuda.synchronize()

    for bs in batch_sizes:
        batch_np = features[:bs]
        actual = int(batch_np.shape[0])
        if mode == "model_only_on_device":
            tensor = torch.from_numpy(batch_np).to(device)
            sync()

            def make_fn(t=tensor):
                def _fn() -> None:
                    with torch.no_grad():
                        _ = model(t)

                return _fn

            fn = make_fn()
        elif mode == "with_h2d":

            def make_fn(arr=batch_np):
                def _fn() -> None:
                    t = torch.from_numpy(arr).to(device)
                    with torch.no_grad():
                        _ = model(t)

                return _fn

            fn = make_fn()
        else:
            raise ValueError(mode)

        rep_stats = []
        for r in range(repeats):
            stats = time_callable(fn, warmup=warmup, timed=timed, sync=sync)
            stats["repeat"] = r + 1
            stats["throughput_samples_per_s"] = (
                actual / (stats["latency_mean_ms"] / 1000.0)
                if stats["latency_mean_ms"] > 0
                else float("nan")
            )
            rep_stats.append(stats)
        summary = summarize(rep_stats)
        tps = float(
            np.mean([s["throughput_samples_per_s"] for s in rep_stats])
        )
        rows.append(
            {
                "variant": f"pytorch_{device.type}_fp32",
                "mode": mode,
                "batch_size": actual,
                "device": str(device),
                "execution_provider": f"pytorch:{device.type}",
                **summary,
                "throughput_samples_per_s_mean_over_repeats": tps,
                "repeats": repeats,
                "warmup_runs": warmup,
                "timed_runs": timed,
            }
        )
    return rows


def run_ort_variant(
    sess,
    features: np.ndarray,
    *,
    label: str,
    provider: str,
    mode: str,
    batch_sizes: list[int],
    warmup: int,
    timed: int,
    repeats: int,
) -> list[dict[str, Any]]:
    rows = []
    inp_name = sess.get_inputs()[0].name
    used = sess.get_providers()
    if provider == "CUDAExecutionProvider" and used[0] != "CUDAExecutionProvider":
        raise RuntimeError(f"ORT session not on CUDA: {used}")

    for bs in batch_sizes:
        batch_np = np.ascontiguousarray(features[:bs], dtype=np.float32)
        actual = int(batch_np.shape[0])

        cuda_sync_needed = provider == "CUDAExecutionProvider" and torch.cuda.is_available()

        def sync() -> None:
            if cuda_sync_needed:
                torch.cuda.synchronize()

        if mode == "with_h2d":

            def make_fn(arr=batch_np):
                def _fn() -> None:
                    _ = sess.run(None, {inp_name: arr})

                return _fn

            fn = make_fn()
        elif mode == "model_only_on_device" and provider == "CUDAExecutionProvider":
            # IOBinding keeps input on GPU between runs when possible.
            io_binding = sess.io_binding()
            x_ort = torch.from_numpy(batch_np).cuda()
            torch.cuda.synchronize()

            def make_fn(binding=io_binding, tensor=x_ort, name=inp_name, session=sess):
                def _fn() -> None:
                    binding.bind_input(
                        name=name,
                        device_type="cuda",
                        device_id=0,
                        element_type=np.float32,
                        shape=tuple(tensor.shape),
                        buffer_ptr=tensor.data_ptr(),
                    )
                    binding.bind_output(session.get_outputs()[0].name, "cuda")
                    session.run_with_iobinding(binding)

                return _fn

            fn = make_fn()
        else:
            # CPU model_only == host memory feed
            def make_fn(arr=batch_np):
                def _fn() -> None:
                    _ = sess.run(None, {inp_name: arr})

                return _fn

            fn = make_fn()
            mode = "model_only_on_device"

        rep_stats = []
        for r in range(repeats):
            stats = time_callable(fn, warmup=warmup, timed=timed, sync=sync)
            stats["repeat"] = r + 1
            stats["throughput_samples_per_s"] = (
                actual / (stats["latency_mean_ms"] / 1000.0)
                if stats["latency_mean_ms"] > 0
                else float("nan")
            )
            rep_stats.append(stats)
        summary = summarize(rep_stats)
        tps = float(np.mean([s["throughput_samples_per_s"] for s in rep_stats]))
        rows.append(
            {
                "variant": label,
                "mode": mode,
                "batch_size": actual,
                "device": provider,
                "execution_provider": used[0],
                "all_providers": used,
                **summary,
                "throughput_samples_per_s_mean_over_repeats": tps,
                "repeats": repeats,
                "warmup_runs": warmup,
                "timed_runs": timed,
            }
        )
    return rows


def try_quant_cuda(quant_path: Path) -> dict[str, Any]:
    if not quant_path.is_file():
        return {
            "status": "SKIPPED_NOT_IN_PACKAGE",
            "reason": "quantized ONNX not included in Colab package",
        }
    try:
        sess = ort_session(quant_path, prefer_cuda=True)
        # smoke one run
        x = np.zeros((1, 47), dtype=np.float32)
        _ = ort_logits(sess, x)
        return {
            "status": "SUPPORTED_SESSION_CREATED",
            "providers": sess.get_providers(),
            "note": "Not timed in default package run; enable explicitly if needed",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "SKIPPED_UNSUPPORTED_OR_CPU_FALLBACK_RISK",
            "reason": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--device-set",
        choices=["cpu", "all"],
        default="all",
        help="cpu = local smoke (PyTorch CPU + ORT CPU only); all = CPU+CUDA",
    )
    parser.add_argument("--batch-sizes", default="1,8,32,64,128")
    parser.add_argument("--warmup", type=int, default=WARMUP)
    parser.add_argument("--timed", type=int, default=TIMED)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    root: Path = args.root
    out_dir = args.output_dir or (root / "out")
    out_dir.mkdir(parents=True, exist_ok=True)

    pt_path = root / "models" / "credit_scoring_nn.pt"
    onnx_path = root / "models" / "credit_scoring_nn.onnx"
    feat_path = root / "data" / "synthetic_features.npy"
    for p in (pt_path, onnx_path, feat_path):
        if not p.is_file():
            raise FileNotFoundError(p)

    features = load_features(feat_path)
    if features.shape[1] != 47:
        raise ValueError(f"expected input_dim=47, got {features.shape[1]}")

    batches = [int(x) for x in args.batch_sizes.split(",") if x.strip()]
    meta = env_metadata()
    model_cpu = load_mlp_checkpoint(str(pt_path), map_location="cpu")

    report: dict[str, Any] = {
        "status": "completed",
        "benchmark_scope": "model_only_synthetic",
        "quality_evaluation": False,
        "note": (
            "Synthetic standard_normal features — latency/throughput only. "
            "NOT a holdout quality score."
        ),
        "experiment": {
            "batch_sizes": batches,
            "warmup_runs": args.warmup,
            "timed_runs": args.timed,
            "repeats": args.repeats,
            "parity_atol": PARITY_ATOL,
            "parity_rtol": PARITY_RTOL,
            "modes": [
                "model_only_on_device",
                "with_h2d",
            ],
        },
        "models": {
            "pytorch_checkpoint": {
                "path": "models/credit_scoring_nn.pt",
                "sha256": sha256_file(pt_path),
                "size_bytes": pt_path.stat().st_size,
            },
            "onnx_fp32": {
                "path": "models/credit_scoring_nn.onnx",
                "sha256": sha256_file(onnx_path),
                "size_bytes": onnx_path.stat().st_size,
            },
        },
        "inputs": json.loads(
            (root / "data" / "synthetic_features_meta.json").read_text(encoding="utf-8")
        ),
        "environment": meta,
        "results": [],
        "parity": [],
        "ort_cuda_profile": None,
        "quantized_gpu": try_quant_cuda(root / "models" / "credit_scoring_nn.quant.onnx"),
    }

    # --- CPU baselines ---
    report["results"].extend(
        run_torch_variant(
            model_cpu,
            features,
            device=torch.device("cpu"),
            mode="model_only_on_device",
            batch_sizes=batches,
            warmup=args.warmup,
            timed=args.timed,
            repeats=args.repeats,
        )
    )
    cpu_sess = ort_session(onnx_path, prefer_cuda=False)
    report["results"].extend(
        run_ort_variant(
            cpu_sess,
            features,
            label="onnx_cpu_fp32",
            provider="CPUExecutionProvider",
            mode="model_only_on_device",
            batch_sizes=batches,
            warmup=args.warmup,
            timed=args.timed,
            repeats=args.repeats,
        )
    )

    ref_batch = features[: min(128, len(features))]
    pt_cpu_out = torch_logits(model_cpu, ref_batch, torch.device("cpu"))
    ort_cpu_out = ort_logits(cpu_sess, ref_batch)
    report["parity"].append(
        compare_outputs(pt_cpu_out, ort_cpu_out, "pytorch_cpu_vs_onnx_cpu")
    )

    if args.device_set == "all":
        if not torch.cuda.is_available():
            report["status"] = "PARTIAL_CPU_ONLY"
            report["gpu_status"] = "BLOCKED_NO_GPU"
            report["gpu_reason"] = "torch.cuda.is_available() is False"
        else:
            import onnxruntime as ort

            if "CUDAExecutionProvider" not in ort.get_available_providers():
                report["status"] = "PARTIAL_CPU_ONLY"
                report["gpu_status"] = "BLOCKED_NO_CUDA_EP"
            else:
                report["gpu_status"] = "RUNNING"
                # PyTorch CUDA modes
                model_gpu = load_mlp_checkpoint(str(pt_path), map_location="cpu")
                for mode in ("model_only_on_device", "with_h2d"):
                    report["results"].extend(
                        run_torch_variant(
                            model_gpu,
                            features,
                            device=torch.device("cuda"),
                            mode=mode,
                            batch_sizes=batches,
                            warmup=args.warmup,
                            timed=args.timed,
                            repeats=args.repeats,
                        )
                    )
                pt_gpu_out = torch_logits(model_gpu, ref_batch, torch.device("cuda"))
                report["parity"].append(
                    compare_outputs(pt_cpu_out, pt_gpu_out, "pytorch_cpu_vs_pytorch_cuda")
                )

                cuda_sess = ort_session(onnx_path, prefer_cuda=True)
                assert cuda_sess.get_providers()[0] == "CUDAExecutionProvider"
                for mode in ("model_only_on_device", "with_h2d"):
                    report["results"].extend(
                        run_ort_variant(
                            cuda_sess,
                            features,
                            label="onnx_cuda_fp32",
                            provider="CUDAExecutionProvider",
                            mode=mode,
                            batch_sizes=batches,
                            warmup=args.warmup,
                            timed=args.timed,
                            repeats=args.repeats,
                        )
                    )
                ort_cuda_out = ort_logits(cuda_sess, ref_batch)
                report["parity"].append(
                    compare_outputs(ort_cpu_out, ort_cuda_out, "onnx_cpu_vs_onnx_cuda")
                )
                report["parity"].append(
                    compare_outputs(pt_gpu_out, ort_cuda_out, "pytorch_cuda_vs_onnx_cuda")
                )
                report["ort_cuda_profile"] = profile_ort_cuda_ops(
                    onnx_path, features[:8]
                )
                if report["status"] == "completed":
                    report["gpu_status"] = "VERIFIED_GPU"

    # Fail hard if any required parity failed
    failed = [p for p in report["parity"] if not p.get("passed")]
    if failed:
        report["parity_status"] = "FAIL"
        report["status"] = "FAILED_PARITY"
    else:
        report["parity_status"] = "PASS"

    json_path = out_dir / "colab_gpu_benchmark.json"
    csv_path = out_dir / "colab_gpu_benchmark.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    fields = [
        "variant",
        "mode",
        "batch_size",
        "device",
        "execution_provider",
        "latency_mean_ms_mean_over_repeats",
        "latency_p50_ms_mean_over_repeats",
        "latency_p95_ms_mean_over_repeats",
        "latency_p99_ms_mean_over_repeats",
        "throughput_samples_per_s_mean_over_repeats",
        "warmup_runs",
        "timed_runs",
        "repeats",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in report["results"]:
            w.writerow(row)

    print(json.dumps({"output_json": str(json_path), "output_csv": str(csv_path), "status": report["status"], "parity": report["parity_status"], "n_rows": len(report["results"])}, indent=2))
    return 0 if report["status"] in {"completed", "PARTIAL_CPU_ONLY"} and report["parity_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
