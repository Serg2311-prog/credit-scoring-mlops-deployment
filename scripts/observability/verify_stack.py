"""Stage 5 observability verification (PASS/FAIL, non-zero on failure)."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _get(url: str, timeout: float = 8.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read()


def _get_json(url: str) -> Any:
    _, body = _get(url)
    return json.loads(body.decode("utf-8"))


def check_http(name: str, url: str, expect_substr: str | None = None) -> Check:
    try:
        status, body = _get(url)
        text = body.decode("utf-8", errors="replace")
        if status >= 400:
            return Check(name, False, f"HTTP {status}")
        if expect_substr and expect_substr not in text:
            return Check(name, False, f"missing substring {expect_substr!r}")
        return Check(name, True, f"HTTP {status}")
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, str(exc))


def check_prometheus_targets(base: str) -> Check:
    try:
        data = _get_json(f"{base}/api/v1/targets")
        active = data.get("data", {}).get("activeTargets", [])
        api = [
            t for t in active if t.get("labels", {}).get("job") == "credit-scoring-api"
        ]
        if not api:
            return Check(
                "prometheus_api_target", False, "job credit-scoring-api not found"
            )
        health = api[0].get("health")
        if health != "up":
            return Check("prometheus_api_target", False, f"health={health}")
        return Check("prometheus_api_target", True, "health=up")
    except Exception as exc:  # noqa: BLE001
        return Check("prometheus_api_target", False, str(exc))


def check_prometheus_rules(base: str) -> Check:
    try:
        data = _get_json(f"{base}/api/v1/rules")
        groups = data.get("data", {}).get("groups", [])
        names = {
            rule.get("name") for group in groups for rule in group.get("rules", [])
        }
        required = {
            "APIDown",
            "HighHTTP5xxRate",
            "HighP95Latency",
            "ModelNotReady",
            "APIMetricsAbsent",
        }
        missing = sorted(required - names)
        if missing:
            return Check("prometheus_alert_rules", False, f"missing={missing}")
        return Check("prometheus_alert_rules", True, f"loaded={len(required)}")
    except Exception as exc:  # noqa: BLE001
        return Check("prometheus_alert_rules", False, str(exc))


def check_grafana_datasources(base: str, user: str, password: str) -> Check:
    try:
        url = f"{base}/api/datasources"
        req = urllib.request.Request(url)
        import base64

        auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {auth}")
        with urllib.request.urlopen(req, timeout=8) as resp:
            items = json.loads(resp.read().decode("utf-8"))
        types = {d.get("type") for d in items}
        if "prometheus" not in types or "loki" not in types:
            return Check("grafana_datasources", False, f"types={sorted(types)}")
        return Check("grafana_datasources", True, "prometheus+loki")
    except Exception as exc:  # noqa: BLE001
        return Check("grafana_datasources", False, str(exc))


def check_loki_has_labels(base: str) -> Check:
    try:
        data = _get_json(f"{base}/loki/api/v1/labels")
        labels = set(data.get("data") or [])
        # Fresh stack may need a moment for first log push.
        if not labels:
            return Check("loki_labels", False, "no labels yet (generate API traffic)")
        return Check("loki_labels", True, f"labels={sorted(labels)[:8]}")
    except Exception as exc:  # noqa: BLE001
        return Check("loki_labels", False, str(exc))


def check_api_metrics(base: str) -> Check:
    try:
        _, body = _get(f"{base}/metrics")
        text = body.decode("utf-8", errors="replace")
        required = [
            "credit_scoring_http_requests_total",
            "credit_scoring_http_request_latency_seconds",
            "credit_scoring_inference_latency_seconds",
            "credit_scoring_model_ready",
        ]
        missing = [m for m in required if m not in text]
        if missing:
            return Check("api_metrics", False, f"missing={missing}")
        return Check("api_metrics", True, "core metrics present")
    except Exception as exc:  # noqa: BLE001
        return Check("api_metrics", False, str(exc))


def check_alertmanager(base: str) -> Check:
    return check_http("alertmanager_ready", f"{base}/-/ready")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--prometheus", default="http://127.0.0.1:9090")
    parser.add_argument("--grafana", default="http://127.0.0.1:3000")
    parser.add_argument("--loki", default="http://127.0.0.1:3100")
    parser.add_argument("--alertmanager", default="http://127.0.0.1:9093")
    parser.add_argument("--grafana-user", default="admin")
    parser.add_argument("--grafana-password", default="admin")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=3.0)
    args = parser.parse_args()

    last: list[Check] = []
    for attempt in range(1, args.retries + 1):
        checks = [
            check_http("prometheus_ready", f"{args.prometheus}/-/ready"),
            check_prometheus_targets(args.prometheus),
            check_prometheus_rules(args.prometheus),
            check_http("loki_ready", f"{args.loki}/ready"),
            check_loki_has_labels(args.loki),
            check_grafana_datasources(
                args.grafana, args.grafana_user, args.grafana_password
            ),
            check_http("grafana_health", f"{args.grafana}/api/health", "database"),
            check_alertmanager(args.alertmanager),
            check_api_metrics(args.api),
            check_http("api_live", f"{args.api}/health/live", "ok"),
        ]
        last = checks
        failed = [c for c in checks if not c.ok]
        if not failed:
            break
        if attempt < args.retries:
            time.sleep(args.sleep)

    print("=== Stage 5 observability checks ===")
    failed = []
    for check in last:
        status = "PASS" if check.ok else "FAIL"
        print(f"[{status}] {check.name}: {check.detail}")
        if not check.ok:
            failed.append(check.name)

    if failed:
        print(f"RESULT: FAIL ({len(failed)} checks)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
