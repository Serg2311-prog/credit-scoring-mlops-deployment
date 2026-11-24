"""Concurrent HTTP load test for FastAPI inference (synthetic requests only).

Stops early if free RAM drops below --min-free-mb to avoid OOM on small laptops.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _free_mb() -> float:
    return psutil.virtual_memory().available / (1024 * 1024)


def run_level(
    client: httpx.Client,
    *,
    concurrency: int,
    duration_s: float,
    timeout_s: float,
    stop_event: threading.Event,
    min_free_mb: float,
) -> dict:
    latencies: list[float] = []
    errors = 0
    timeouts = 0
    ok = 0
    lock = threading.Lock()
    deadline = time.perf_counter() + duration_s

    def worker() -> None:
        nonlocal errors, timeouts, ok
        while time.perf_counter() < deadline and not stop_event.is_set():
            if _free_mb() < min_free_mb:
                stop_event.set()
                break
            started = time.perf_counter()
            try:
                resp = client.post("/predict", json=SAMPLE, timeout=timeout_s)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                with lock:
                    if resp.status_code == 200:
                        ok += 1
                        latencies.append(elapsed_ms)
                    else:
                        errors += 1
            except httpx.TimeoutException:
                with lock:
                    timeouts += 1
            except Exception:
                with lock:
                    errors += 1

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(concurrency)]
        for fut in as_completed(futures):
            fut.result()

    total = ok + errors + timeouts
    wall = duration_s
    return {
        "concurrency": concurrency,
        "duration_s": duration_s,
        "requests_ok": ok,
        "http_errors": errors,
        "timeouts": timeouts,
        "rps": ok / wall if wall > 0 else float("nan"),
        "error_rate": (errors + timeouts) / total if total else 0.0,
        "latency_p50_ms": float(statistics.median(latencies)) if latencies else None,
        "latency_p95_ms": (
            float(statistics.quantiles(latencies, n=20)[18])
            if len(latencies) >= 20
            else (max(latencies) if latencies else None)
        ),
        "latency_p99_ms": (
            float(statistics.quantiles(latencies, n=100)[98])
            if len(latencies) >= 100
            else (max(latencies) if latencies else None)
        ),
        "latency_mean_ms": float(statistics.mean(latencies)) if latencies else None,
        "stopped_early": stop_event.is_set(),
        "free_mb_end": _free_mb(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--concurrency",
        default="1,2,4,8",
        help="Comma-separated concurrency levels",
    )
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--min-free-mb", type=float, default=400.0)
    parser.add_argument(
        "--output",
        default="",
        help="JSON output path (default artifacts/block7/api_load_test.json)",
    )
    args = parser.parse_args()
    levels = [int(x) for x in args.concurrency.split(",") if x.strip()]

    stop = threading.Event()
    host_rss = psutil.Process().memory_info().rss / (1024 * 1024)
    results = []
    health_after = {}

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        for path in ("/health/live", "/health/ready"):
            r = client.get(path)
            r.raise_for_status()
        for conc in levels:
            if _free_mb() < args.min_free_mb:
                results.append(
                    {
                        "concurrency": conc,
                        "skipped": True,
                        "reason": f"free_mb<{args.min_free_mb}",
                        "free_mb": _free_mb(),
                    }
                )
                break
            print(f"==> concurrency={conc} duration={args.duration}s")
            stop.clear()
            row = run_level(
                client,
                concurrency=conc,
                duration_s=args.duration,
                timeout_s=args.timeout,
                stop_event=stop,
                min_free_mb=args.min_free_mb,
            )
            results.append(row)
            print(
                f"  rps={row['rps']:.2f} p95={row['latency_p95_ms']} "
                f"err={row['error_rate']:.3f} early={row['stopped_early']}"
            )
            if row["stopped_early"] or row["error_rate"] > 0.05:
                print("Stopping higher concurrency (saturation / memory / errors)")
                break

        for path in ("/health/live", "/health/ready"):
            r = client.get(path)
            health_after[path] = {
                "status_code": r.status_code,
                "ok": r.status_code == 200,
            }

    # Saturation = last level before skip/stop, or last completed
    completed = [r for r in results if not r.get("skipped")]
    safe = None
    for row in completed:
        if row.get("error_rate", 1) <= 0.01 and not row.get("stopped_early"):
            safe = row["concurrency"]
    report = {
        "environment": "local_http",
        "base_url": args.base_url,
        "host_process_rss_mb": host_rss,
        "free_mb_start": _free_mb(),
        "min_free_mb": args.min_free_mb,
        "levels": results,
        "recommended_safe_concurrency": safe,
        "health_after": health_after,
        "status": "completed",
        "notes": (
            "Synthetic payloads only. Local laptop evidence — not cloud SKU proof."
        ),
    }
    out = (
        Path(args.output)
        if args.output
        else artifacts_dir() / "block7" / "api_load_test.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    dump_json(out, report)
    print(json.dumps({"output": str(out), "safe_concurrency": safe}, indent=2))
    return 0 if all(v.get("ok") for v in health_after.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
