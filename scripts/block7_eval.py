"""Block 7 evaluation orchestrator — does NOT retrain or overwrite production models.

Writes reports under artifacts/block7/. Reuses existing .onnx / .quant.onnx / .pt.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import (  # noqa: E402
    artifacts_dir,
    dump_json,
    nn_onnx_path,
    nn_quant_onnx_path,
)
from src.nn.benchmark import benchmark_cpu, benchmark_gpu  # noqa: E402
from src.nn.parity import run_parity  # noqa: E402


def _env_info() -> dict:
    import onnxruntime as ort
    import torch

    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "processor": platform.processor(),
        "torch": torch.__version__,
        "torch_cuda_is_available": bool(torch.cuda.is_available()),
        "onnxruntime": ort.__version__,
        "onnxruntime_providers": list(ort.get_available_providers()),
    }


def quant_delta_report(src: Path) -> dict:
    data = json.loads(src.read_text(encoding="utf-8"))
    fp = data["metrics"]["onnx_fp32"]
    q = data["metrics"]["onnx_quantized"]
    deltas = {}
    for key in ("roc_auc", "pr_auc", "precision", "recall", "f1", "accuracy"):
        a, b = float(fp[key]), float(q[key])
        deltas[key] = {
            "fp32": a,
            "quant": b,
            "abs_delta": b - a,
            "rel_delta": (b - a) / a if a else None,
        }
    size_fp = int(data["source_size_bytes"])
    size_q = int(data["quantized_size_bytes"])
    return {
        "source_artifact": str(src),
        "holdout_n": data["classification_impact"]["n_rows"],
        "threshold": data["classification_impact"]["threshold"],
        "confusion_fp32": {k: fp[k] for k in ("tn", "fp", "fn", "tp") if k in fp},
        "confusion_quant": {k: q[k] for k in ("tn", "fp", "fn", "tp") if k in q},
        "metric_deltas": deltas,
        "size_bytes": {
            "fp32": size_fp,
            "quant": size_q,
            "ratio_quant_to_fp32": size_q / size_fp if size_fp else None,
        },
        "decision_flips": data["classification_impact"],
        "notes": (
            "Metrics from existing quantization evaluation on fixed holdout; "
            "threshold=0.5 not tuned on test. Latency compared in CPU benchmark."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-sizes",
        default="1,8,32,64,128",
        help="CPU benchmark batch sizes",
    )
    parser.add_argument(
        "--thread-configs",
        default="1,2,4",
        help="CPU thread counts to sweep (one full bench per value)",
    )
    parser.add_argument("--skip-cpu", action="store_true")
    parser.add_argument("--skip-parity", action="store_true")
    args = parser.parse_args()

    out_dir = artifacts_dir() / "block7"
    out_dir.mkdir(parents=True, exist_ok=True)
    dump_json(out_dir / "environment.json", _env_info())

    # Confirm production paths exist and are used read-only
    assert nn_onnx_path().is_file(), "production FP32 ONNX missing"
    assert nn_quant_onnx_path().is_file(), "quant ONNX missing"

    if not args.skip_parity:
        print("==> Parity PyTorch vs ONNX FP32 (read-only models)")
        parity = run_parity()
        dump_json(
            out_dir / "parity_summary.json",
            {
                "result": parity.get("result"),
                "passed": parity.get("passed"),
                "n_test_rows": parity.get("n_test_rows"),
                "full_test": parity.get("full_test"),
                "parity_atol": parity.get("parity_atol"),
                "parity_mae_atol": parity.get("parity_mae_atol"),
            },
        )

    quant_src = artifacts_dir() / "onnx_quantization.json"
    if quant_src.is_file():
        dump_json(out_dir / "quantization_deltas.json", quant_delta_report(quant_src))

    batches = [int(x) for x in args.batch_sizes.split(",") if x.strip()]
    threads = [int(x) for x in args.thread_configs.split(",") if x.strip()]

    if not args.skip_cpu:
        # Primary sweep: params threads=2 with Block-7 batch sizes
        print("==> CPU benchmark primary (threads=2)")
        benchmark_cpu(
            batch_sizes=batches,
            num_threads=2,
            output_path=out_dir / "benchmark_cpu_block7.json",
        )
        # Smaller thread matrix at batch=32 only to limit runtime/RAM
        thread_rows = []
        for t in threads:
            print(f"==> CPU thread probe threads={t} batch=32 (model_only, short)")
            report = benchmark_cpu(
                batch_sizes=[32],
                num_threads=t,
                warmup_runs=5,
                timed_runs=30,
                repeats=2,
                scopes=("model_only",),
                output_path=out_dir / f"benchmark_cpu_threads_{t}.json",
            )
            for row in report.get("results_model_only", []):
                thread_rows.append(
                    {
                        "threads": t,
                        "variant": row["variant"],
                        "batch_size": row["batch_size"],
                        "p50_ms": row["latency_p50_ms_mean_over_repeats"],
                        "p95_ms": row["latency_p95_ms_mean_over_repeats"],
                        "p99_ms": row.get("latency_p99_ms_mean_over_repeats"),
                        "throughput": row["throughput_samples_per_s_mean_over_repeats"],
                    }
                )
        dump_json(out_dir / "cpu_thread_probe.json", {"rows": thread_rows})

    print("==> GPU benchmark (expect BLOCKED_NO_GPU on this laptop)")
    benchmark_gpu(output_path=out_dir / "benchmark_gpu.json")
    # Also refresh top-level artifact for compatibility
    benchmark_gpu(output_path=artifacts_dir() / "benchmark_gpu.json")

    print(f"Block 7 artifacts in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
