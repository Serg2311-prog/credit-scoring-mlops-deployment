#!/usr/bin/env python3
"""Hardened CPU/GPU model-only benchmark (synthetic inputs).

Improvements vs historical Colab runner (results/block7/colab/historical_runner/):
- ORT session.disable_cpu_ep_fallback=1 + sess.disable_fallback()
- Structured Node-event profiling (args.provider); VERIFIED_GPU only if CUDA-only
- Profiling session separate from timed measurements
- IOBinding bind setup outside timed loop for model_only_on_device
- Explicit mode semantics for PyTorch H2D vs ORT host I/O
- Input validation (shape/dtype/finite/SHA256/batch sizes)
- Non-zero exit when --require-gpu and CUDA/profile/parity fail

Historical Colab numbers must not be overwritten by this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Allow importing src.nn.ort_profiling when run from repo root
_REPO = ROOT.parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from mlp_model import load_mlp_checkpoint  # noqa: E402

try:
    from ort_profiling import load_ort_profile, require_cuda_only_nodes  # noqa: E402
except ImportError:  # package layout inside repo
    from src.nn.ort_profiling import (  # noqa: E402
        load_ort_profile,
        require_cuda_only_nodes,
    )

DEFAULT_BATCHES = [1, 8, 32, 64, 128]
WARMUP = 20
TIMED = 100
REPEATS = 3
PARITY_ATOL = 1e-5
PARITY_RTOL = 1e-4
INPUT_DIM = 47


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
        started = time.perf_counter()
        fn()
        if sync:
            sync()
        samples.append((time.perf_counter() - started) * 1000.0)
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
    keys = ["latency_mean_ms", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"]
    return {
        f"{key}_mean_over_repeats": float(np.mean([row[key] for row in repeats]))
        for key in keys
    }


def validate_features(
    features: np.ndarray,
    *,
    expected_sha256: str | None,
    batch_sizes: list[int],
) -> dict[str, Any]:
    if features.ndim != 2:
        raise ValueError("features must be 2D [N, input_dim]")
    if features.dtype != np.float32:
        raise ValueError(f"features dtype must be float32, got {features.dtype}")
    if int(features.shape[1]) != INPUT_DIM:
        raise ValueError(f"expected input_dim={INPUT_DIM}, got {features.shape[1]}")
    if not np.isfinite(features).all():
        raise ValueError("features contain non-finite values")
    if features.shape[0] < max(batch_sizes):
        raise ValueError(
            f"need >= max(batch_sizes)={max(batch_sizes)} rows, "
            f"got {features.shape[0]}"
        )
    digest = sha256_bytes(np.ascontiguousarray(features).tobytes())
    if expected_sha256 and digest != expected_sha256:
        raise ValueError(
            f"synthetic SHA256 mismatch: got {digest}, " f"expected {expected_sha256}"
        )
    return {
        "shape": list(features.shape),
        "dtype": str(features.dtype),
        "finite": True,
        "sha256": digest,
        "sha256_checked": bool(expected_sha256),
    }


def env_metadata(*, num_threads: int | None) -> dict[str, Any]:
    import onnxruntime as ort

    meta: dict[str, Any] = {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "torch_cuda_is_available": bool(torch.cuda.is_available()),
        "torch_num_threads": torch.get_num_threads(),
        "configured_num_threads": num_threads,
        "onnxruntime": ort.__version__,
        "onnxruntime_providers": list(ort.get_available_providers()),
    }
    if torch.cuda.is_available():
        meta["cuda_device_name"] = torch.cuda.get_device_name(0)
        meta["cuda_device_count"] = torch.cuda.device_count()
        meta["cuda_runtime_version"] = getattr(torch.version, "cuda", None)
    return meta


def configure_threads(num_threads: int | None) -> int:
    threads = int(num_threads if num_threads is not None else 2)
    threads = max(1, threads)
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(threads))
    torch.set_num_threads(threads)
    return threads


def compare_outputs(a: np.ndarray, b: np.ndarray, name: str) -> dict[str, Any]:
    a_arr = np.asarray(a, dtype=np.float64).reshape(-1)
    b_arr = np.asarray(b, dtype=np.float64).reshape(-1)
    abs_err = np.abs(a_arr - b_arr)
    rel = abs_err / np.maximum(np.abs(a_arr), 1e-12)
    passed = bool(np.all(abs_err <= (PARITY_ATOL + PARITY_RTOL * np.abs(a_arr))))
    return {
        "pair": name,
        "n": int(a_arr.size),
        "max_abs": float(abs_err.max()),
        "mae": float(abs_err.mean()),
        "max_rel": float(rel.max()),
        "atol": PARITY_ATOL,
        "rtol": PARITY_RTOL,
        "passed": passed,
    }


def ort_session(model_path: Path, *, prefer_cuda: bool):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if prefer_cuda:
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("CUDAExecutionProvider not available")
        session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CUDAExecutionProvider"],
        )
        if hasattr(session, "disable_fallback"):
            session.disable_fallback()
        used = list(session.get_providers())
        if not used or used[0] != "CUDAExecutionProvider":
            raise RuntimeError(f"ORT CUDA primary provider failed: {used}")
        return session
    session = ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    return session


def profile_ort_cuda_separate(
    model_path: Path, batch: np.ndarray, out_dir: Path
) -> dict:
    """Profile a dedicated session (overhead not included in latency benches)."""
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.enable_profiling = True
    options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    session = ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CUDAExecutionProvider"],
    )
    if hasattr(session, "disable_fallback"):
        session.disable_fallback()
    if session.get_providers()[0] != "CUDAExecutionProvider":
        raise RuntimeError("profiling session primary provider is not CUDA")
    name = session.get_inputs()[0].name
    _ = session.run(None, {name: batch.astype(np.float32)})
    profile_path = Path(session.end_profiling())
    dest = out_dir / profile_path.name
    dest.write_bytes(profile_path.read_bytes())
    events = load_ort_profile(dest)
    analysis = require_cuda_only_nodes(events)
    analysis["profile_file"] = dest.name
    analysis["primary_provider"] = session.get_providers()[0]
    return analysis


def torch_logits(model, batch: np.ndarray, device: torch.device) -> np.ndarray:
    tensor = torch.from_numpy(batch).to(device)
    with torch.no_grad():
        out = model(tensor)
        if device.type == "cuda":
            torch.cuda.synchronize()
        return out.detach().cpu().numpy().astype(np.float64)


def ort_logits(session, batch: np.ndarray) -> np.ndarray:
    name = session.get_inputs()[0].name
    out = session.run(None, {name: batch.astype(np.float32)})[0]
    return np.asarray(out, dtype=np.float64).reshape(-1)


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
    rows: list[dict[str, Any]] = []
    model = model.to(device).eval()
    if device.type == "cuda" and next(model.parameters()).device.type != "cuda":
        raise RuntimeError("PyTorch model parameters are not on CUDA")

    def sync() -> None:
        if device.type == "cuda":
            torch.cuda.synchronize()

    mode_note = {
        "model_only_on_device": (
            "Input tensor pre-placed on device; timed region is forward (+sync)"
        ),
        "with_h2d": (
            "Timed region includes host->device copy of inputs; "
            "optional sync; no extra D2H in timed fn"
        ),
    }

    for batch_size in batch_sizes:
        batch_np = features[:batch_size]
        actual = int(batch_np.shape[0])
        if mode == "model_only_on_device":
            tensor = torch.from_numpy(batch_np).to(device)
            sync()

            def fn(t=tensor) -> None:
                with torch.no_grad():
                    _ = model(t)

        elif mode == "with_h2d":

            def fn(arr=batch_np) -> None:
                tensor = torch.from_numpy(arr).to(device)
                with torch.no_grad():
                    _ = model(tensor)

        else:
            raise ValueError(mode)

        rep_stats = []
        for repeat_idx in range(repeats):
            stats = time_callable(fn, warmup=warmup, timed=timed, sync=sync)
            stats["repeat"] = repeat_idx + 1
            stats["throughput_samples_per_s"] = (
                actual / (stats["latency_mean_ms"] / 1000.0)
                if stats["latency_mean_ms"] > 0
                else float("nan")
            )
            rep_stats.append(stats)
        summary = summarize(rep_stats)
        tps = float(np.mean([item["throughput_samples_per_s"] for item in rep_stats]))
        rows.append(
            {
                "variant": f"pytorch_{device.type}_fp32",
                "mode": mode,
                "mode_note": mode_note[mode],
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
    session,
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
    rows: list[dict[str, Any]] = []
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    used = list(session.get_providers())
    if provider == "CUDAExecutionProvider" and used[0] != "CUDAExecutionProvider":
        raise RuntimeError(f"ORT session not on CUDA: {used}")

    mode_note = {
        "model_only_on_device": (
            "CUDA IOBinding: input buffer pre-bound on GPU; bind_* calls are outside "
            "the timed loop; timed region is run_with_iobinding + sync. "
            "Outputs remain on GPU (not equivalent to host-output fetch)."
        ),
        "with_h2d": (
            "ORT sess.run with numpy host inputs; timed region includes H2D and "
            "typically D2H for returned numpy outputs — not the same as "
            "PyTorch with_h2d."
        ),
    }

    cuda_sync_needed = provider == "CUDAExecutionProvider" and torch.cuda.is_available()

    def sync() -> None:
        if cuda_sync_needed:
            torch.cuda.synchronize()

    for batch_size in batch_sizes:
        batch_np = np.ascontiguousarray(features[:batch_size], dtype=np.float32)
        actual = int(batch_np.shape[0])

        if mode == "model_only_on_device" and provider == "CUDAExecutionProvider":
            io_binding = session.io_binding()
            tensor = torch.from_numpy(batch_np).cuda()
            # Setup outside timed loop
            io_binding.bind_input(
                name=input_name,
                device_type="cuda",
                device_id=0,
                element_type=np.float32,
                shape=tuple(tensor.shape),
                buffer_ptr=tensor.data_ptr(),
            )
            io_binding.bind_output(output_name, "cuda")
            torch.cuda.synchronize()

            def fn(binding=io_binding, sess=session) -> None:
                sess.run_with_iobinding(binding)

        elif mode == "with_h2d" or provider == "CPUExecutionProvider":

            def fn(arr=batch_np, name=input_name, sess=session) -> None:
                _ = sess.run(None, {name: arr})

            if provider == "CPUExecutionProvider":
                mode = "model_only_on_device"
                mode_note_key = "model_only_on_device"
            else:
                mode_note_key = "with_h2d"
        else:
            raise ValueError(mode)

        if mode == "model_only_on_device" and provider == "CUDAExecutionProvider":
            mode_note_key = "model_only_on_device"
        elif provider == "CPUExecutionProvider":
            mode_note_key = "model_only_on_device"
        else:
            mode_note_key = mode

        rep_stats = []
        for repeat_idx in range(repeats):
            stats = time_callable(
                fn,
                warmup=warmup,
                timed=timed,
                sync=sync if cuda_sync_needed else None,
            )
            stats["repeat"] = repeat_idx + 1
            stats["throughput_samples_per_s"] = (
                actual / (stats["latency_mean_ms"] / 1000.0)
                if stats["latency_mean_ms"] > 0
                else float("nan")
            )
            rep_stats.append(stats)
        summary = summarize(rep_stats)
        tps = float(np.mean([item["throughput_samples_per_s"] for item in rep_stats]))
        rows.append(
            {
                "variant": label,
                "mode": (
                    mode
                    if provider != "CPUExecutionProvider"
                    else "model_only_on_device"
                ),
                "mode_note": mode_note[mode_note_key],
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--device-set", choices=["cpu", "all"], default="all")
    parser.add_argument(
        "--require-gpu",
        action="store_true",
        help="Non-zero exit if CUDA/profile/parity fail (for Colab re-runs)",
    )
    parser.add_argument("--batch-sizes", default="1,8,32,64,128")
    parser.add_argument("--warmup", type=int, default=WARMUP)
    parser.add_argument("--timed", type=int, default=TIMED)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    root: Path = args.root
    out_dir = args.output_dir or (root / "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    threads = configure_threads(args.threads)

    pt_path = root / "models" / "credit_scoring_nn.pt"
    onnx_path = root / "models" / "credit_scoring_nn.onnx"
    feat_path = root / "data" / "synthetic_features.npy"
    meta_path = root / "data" / "synthetic_features_meta.json"
    for path in (pt_path, onnx_path, feat_path, meta_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    features = np.load(feat_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    batches = [int(item) for item in args.batch_sizes.split(",") if item.strip()]
    input_info = validate_features(
        features,
        expected_sha256=meta.get("sha256"),
        batch_sizes=batches,
    )

    report: dict[str, Any] = {
        "status": "completed",
        "runner": "scripts/gpu_benchmark/run_benchmark.py",
        "runner_generation": "hardened_block73",
        "benchmark_scope": "model_only_synthetic",
        "quality_evaluation": False,
        "note": (
            "Synthetic inputs — latency/throughput only. NOT holdout quality. "
            "Historical Colab evidence lives in results/block7/colab/."
        ),
        "experiment": {
            "batch_sizes": batches,
            "warmup_runs": args.warmup,
            "timed_runs": args.timed,
            "repeats": args.repeats,
            "parity_atol": PARITY_ATOL,
            "parity_rtol": PARITY_RTOL,
            "num_threads": threads,
            "modes": ["model_only_on_device", "with_h2d"],
            "mode_semantics": {
                "pytorch_with_h2d": "H2D input copy in timed region; no timed D2H",
                "ort_with_h2d": (
                    "numpy sess.run — typically H2D + D2H for returned outputs"
                ),
                "ort_model_only_on_device": (
                    "IOBinding setup outside timed loop; GPU outputs"
                ),
            },
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
        "inputs": {**meta, **input_info},
        "environment": env_metadata(num_threads=threads),
        "results": [],
        "parity": [],
        "ort_cuda_profile": None,
        "gpu_status": None,
        "quantized_gpu": {
            "status": "NOT_EXECUTED",
            "reason": "Quantized GPU inference not part of this package",
        },
    }

    model_cpu = load_mlp_checkpoint(str(pt_path), map_location="cpu")
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
    cpu_session = ort_session(onnx_path, prefer_cuda=False)
    report["results"].extend(
        run_ort_variant(
            cpu_session,
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

    ref = features[: min(128, len(features))]
    pt_cpu = torch_logits(model_cpu, ref, torch.device("cpu"))
    ort_cpu = ort_logits(cpu_session, ref)
    report["parity"].append(compare_outputs(pt_cpu, ort_cpu, "pytorch_cpu_vs_onnx_cpu"))

    gpu_ok = False
    if args.device_set == "all":
        import onnxruntime as ort

        if not torch.cuda.is_available():
            report["gpu_status"] = "BLOCKED_NO_GPU"
            report["status"] = "PARTIAL_CPU_ONLY"
        elif "CUDAExecutionProvider" not in ort.get_available_providers():
            report["gpu_status"] = "BLOCKED_NO_CUDA_EP"
            report["status"] = "PARTIAL_CPU_ONLY"
        else:
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
            pt_gpu = torch_logits(model_gpu, ref, torch.device("cuda"))
            report["parity"].append(
                compare_outputs(pt_cpu, pt_gpu, "pytorch_cpu_vs_pytorch_cuda")
            )

            cuda_session = ort_session(onnx_path, prefer_cuda=True)
            for mode in ("model_only_on_device", "with_h2d"):
                report["results"].extend(
                    run_ort_variant(
                        cuda_session,
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
            ort_gpu = ort_logits(cuda_session, ref)
            report["parity"].append(
                compare_outputs(ort_cpu, ort_gpu, "onnx_cpu_vs_onnx_cuda")
            )
            report["parity"].append(
                compare_outputs(pt_gpu, ort_gpu, "pytorch_cuda_vs_onnx_cuda")
            )

            # Separate profiling session — not mixed into latency timings
            report["ort_cuda_profile"] = profile_ort_cuda_separate(
                onnx_path, features[:8], out_dir
            )
            gpu_ok = report["ort_cuda_profile"]["status"] == "PASS"
            report["gpu_status"] = "VERIFIED_GPU" if gpu_ok else "FAILED_PROFILE"
            if not gpu_ok:
                report["status"] = "FAILED_PROFILE"

    failed_parity = [item for item in report["parity"] if not item.get("passed")]
    if failed_parity:
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
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in report["results"]:
            writer.writerow(row)

    print(
        json.dumps(
            {
                "output_json": str(json_path),
                "output_csv": str(csv_path),
                "status": report["status"],
                "parity": report["parity_status"],
                "gpu_status": report.get("gpu_status"),
                "n_rows": len(report["results"]),
            },
            indent=2,
        )
    )

    if args.require_gpu:
        if report.get("gpu_status") != "VERIFIED_GPU":
            return 2
        if report["parity_status"] != "PASS":
            return 3
        return 0
    if report["parity_status"] != "PASS":
        return 1
    if report["status"] in {"completed", "PARTIAL_CPU_ONLY"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
