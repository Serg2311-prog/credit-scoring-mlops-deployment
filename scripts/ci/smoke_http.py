"""Post-deploy HTTP smoke: live/ready/metrics/model + valid/invalid predict."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SAMPLE = {
    "LIMIT_BAL": 20000,
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
    "BILL_AMT1": 3913,
    "BILL_AMT2": 3102,
    "BILL_AMT3": 689,
    "BILL_AMT4": 0,
    "BILL_AMT5": 0,
    "BILL_AMT6": 0,
    "PAY_AMT1": 0,
    "PAY_AMT2": 689,
    "PAY_AMT3": 0,
    "PAY_AMT4": 0,
    "PAY_AMT5": 0,
    "PAY_AMT6": 0,
}


def _request(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    host: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if host:
        headers["Host"] = host
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = raw
            return int(resp.status), payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {"detail": str(exc)}
        except json.JSONDecodeError:
            payload = {"detail": raw or str(exc)}
        return int(exc.code), payload


def run_smoke(
    base_url: str,
    *,
    host: str | None = None,
    expect_model_version: str | None = None,
    check_frontend: bool = True,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    results: dict[str, Any] = {"base_url": base, "host": host, "checks": {}}

    code, live = _request(f"{base}/health/live", host=host)
    results["checks"]["live"] = {"status_code": code, "body": live}
    if code != 200 or not (isinstance(live, dict) and live.get("status") == "ok"):
        results["ok"] = False
        results["failed"] = "live"
        return results

    code, ready = _request(f"{base}/health/ready", host=host)
    results["checks"]["ready"] = {"status_code": code, "body": ready}
    if code != 200:
        results["ok"] = False
        results["failed"] = "ready"
        return results

    code, metrics = _request(f"{base}/metrics", host=host)
    results["checks"]["metrics"] = {"status_code": code, "bytes": len(str(metrics))}
    if code != 200 or "credit_scoring_" not in str(metrics):
        results["ok"] = False
        results["failed"] = "metrics"
        return results

    code, model = _request(f"{base}/model/info", host=host)
    results["checks"]["model"] = {"status_code": code, "body": model}
    if code != 200:
        results["ok"] = False
        results["failed"] = "model"
        return results
    if expect_model_version and isinstance(model, dict):
        version = str(model.get("model_version") or model.get("version") or "")
        results["checks"]["model"]["observed_version"] = version
        if expect_model_version not in version:
            results["ok"] = False
            results["failed"] = "model_version_mismatch"
            return results

    code, pred = _request(f"{base}/predict", method="POST", body=SAMPLE, host=host)
    results["checks"]["predict_valid"] = {"status_code": code, "body": pred}
    if code != 200:
        results["ok"] = False
        results["failed"] = "predict_valid"
        return results

    code, bad = _request(
        f"{base}/predict",
        method="POST",
        body={"LIMIT_BAL": "not-a-number"},
        host=host,
    )
    results["checks"]["predict_invalid"] = {"status_code": code, "body": bad}
    if code < 400:
        results["ok"] = False
        results["failed"] = "predict_invalid_should_4xx"
        return results

    if check_frontend:
        code, front = _request(f"{base}/", host=host)
        results["checks"]["frontend"] = {
            "status_code": code,
            "snippet": str(front)[:120],
        }
        if code != 200:
            results["ok"] = False
            results["failed"] = "frontend"
            return results

    results["ok"] = True
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--host", default=None)
    parser.add_argument("--expect-model-version", default=None)
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report = run_smoke(
        args.base_url,
        host=args.host,
        expect_model_version=args.expect_model_version,
        check_frontend=not args.skip_frontend,
    )
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
