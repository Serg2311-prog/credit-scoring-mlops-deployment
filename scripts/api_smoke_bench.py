"""Light HTTP smoke/performance benchmark for inference API."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import artifacts_dir, dump_json  # noqa: E402

SAMPLE = {
    "LIMIT_BAL": 20000.0,
    "SEX": 2,
    "EDUCATION": 2,
    "MARRIAGE": 1,
    "AGE": 24,
    "PAY_0": 2,
    "PAY_2": 2,
    "PAY_3": -1,
    "PAY_4": -1,
    "PAY_5": -2,
    "PAY_6": -2,
    "BILL_AMT1": 3913.0,
    "BILL_AMT2": 3102.0,
    "BILL_AMT3": 689.0,
    "BILL_AMT4": 0.0,
    "BILL_AMT5": 0.0,
    "BILL_AMT6": 0.0,
    "PAY_AMT1": 0.0,
    "PAY_AMT2": 689.0,
    "PAY_AMT3": 0.0,
    "PAY_AMT4": 0.0,
    "PAY_AMT5": 0.0,
    "PAY_AMT6": 0.0,
}


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * q))
    return float(ordered[index])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--timed", type=int, default=30)
    parser.add_argument(
        "--batch-sizes",
        default="1,16,64,256",
        help="Comma-separated batch sizes",
    )
    args = parser.parse_args()
    batch_sizes = [int(item) for item in args.batch_sizes.split(",") if item.strip()]

    process = psutil.Process()
    rss_before = process.memory_info().rss / (1024 * 1024)
    rows = []
    with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
        for path in ("/health/live", "/health/ready", "/model/info", "/metrics"):
            response = client.get(path)
            response.raise_for_status()
        single = client.post("/predict", json=SAMPLE)
        single.raise_for_status()

        for batch_size in batch_sizes:
            payload = {"items": [SAMPLE for _ in range(batch_size)]}
            for _ in range(args.warmup):
                client.post("/predict/batch", json=payload).raise_for_status()
            samples: list[float] = []
            for _ in range(args.timed):
                started = time.perf_counter()
                client.post("/predict/batch", json=payload).raise_for_status()
                samples.append((time.perf_counter() - started) * 1000.0)
            mean = statistics.fmean(samples)
            row = {
                "batch_size": batch_size,
                "p50_ms": percentile(samples, 0.5),
                "p95_ms": percentile(samples, 0.95),
                "mean_ms": mean,
                "throughput_samples_per_s": (
                    batch_size / (mean / 1000.0) if mean > 0 else float("nan")
                ),
                "warmup": args.warmup,
                "timed": args.timed,
            }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))

    rss_after = process.memory_info().rss / (1024 * 1024)
    report = {
        "base_url": args.base_url,
        "note": (
            "HTTP benchmark includes validation+FE+preprocess+ONNX+JSON; "
            "not comparable 1:1 with stage-1 model-only latency."
        ),
        "client_rss_mb_before": rss_before,
        "client_rss_mb_after": rss_after,
        "single_predict_example": single.json(),
        "results": rows,
    }
    destination = artifacts_dir() / "api_benchmark.json"
    dump_json(destination, report)
    print(f"Saved {destination}")


if __name__ == "__main__":
    main()
