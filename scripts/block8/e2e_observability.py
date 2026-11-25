"""Block 8 observability E2E helper — load, metrics, alerts, Loki (no secrets)."""

from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(
    url: str, timeout: float = 10.0, headers: dict | None = None
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read()


def _get_json(url: str, headers: dict | None = None) -> Any:
    _, body = _get(url, headers=headers)
    return json.loads(body.decode("utf-8"))


def _post_json(url: str, payload: dict, timeout: float = 10.0) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return int(resp.status), json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw.decode("utf-8", errors="replace")}
        return int(exc.code), body


def grafana_auth(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def prom_query(base: str, query: str) -> Any:
    q = urllib.parse.urlencode({"query": query})
    return _get_json(f"{base}/api/v1/query?{q}")


def loki_query(base: str, query: str, limit: int = 50) -> Any:
    end_ns = int(time.time() * 1e9)
    start_ns = end_ns - int(15 * 60 * 1e9)
    q = urllib.parse.urlencode(
        {
            "query": query,
            "limit": str(limit),
            "start": str(start_ns),
            "end": str(end_ns),
        }
    )
    return _get_json(f"{base}/loki/api/v1/query_range?{q}")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def cmd_snapshot(args: argparse.Namespace) -> int:
    out = Path(args.output)
    evidence: dict[str, Any] = {"captured_at_utc": _utc(), "status": {}}

    targets = _get_json(f"{args.prometheus}/api/v1/targets")
    evidence["prometheus_targets"] = targets
    active = targets.get("data", {}).get("activeTargets", [])
    evidence["status"]["api_target_up"] = any(
        t.get("labels", {}).get("job") == "credit-scoring-api"
        and t.get("health") == "up"
        for t in active
    )
    evidence["status"]["cadvisor_target_up"] = any(
        t.get("labels", {}).get("job") == "cadvisor" and t.get("health") == "up"
        for t in active
    )

    queries = {
        "request_rate_1m": "sum(rate(credit_scoring_http_requests_total[1m]))",
        "error_rate_5xx_1m": (
            'sum(rate(credit_scoring_http_requests_total{status_code=~"5.."}[1m]))'
        ),
        "inference_count": "sum(credit_scoring_inference_requests_total)",
        "p50_latency": (
            "histogram_quantile(0.50, sum by (le) "
            "(rate(credit_scoring_http_request_latency_seconds_bucket[5m])))"
        ),
        "p95_latency": (
            "histogram_quantile(0.95, sum by (le) "
            "(rate(credit_scoring_http_request_latency_seconds_bucket[5m])))"
        ),
        "p99_latency": (
            "histogram_quantile(0.99, sum by (le) "
            "(rate(credit_scoring_http_request_latency_seconds_bucket[5m])))"
        ),
        "model_ready": "credit_scoring_model_ready",
        "process_cpu": "process_cpu_seconds_total",
        "process_rss": "process_resident_memory_bytes",
        "cadvisor_cpu": "sum(rate(container_cpu_usage_seconds_total[1m]))",
        "cadvisor_memory_docker": 'container_memory_usage_bytes{id="/docker"}',
    }
    evidence["promql"] = {k: prom_query(args.prometheus, q) for k, q in queries.items()}

    rules = _get_json(f"{args.prometheus}/api/v1/rules")
    evidence["prometheus_rules"] = {
        "group_count": len(rules.get("data", {}).get("groups", [])),
        "alerts": [
            {
                "name": r.get("name"),
                "state": r.get("state"),
                "health": r.get("health"),
                "type": r.get("type"),
            }
            for g in rules.get("data", {}).get("groups", [])
            for r in g.get("rules", [])
        ],
    }

    am = _get_json(f"{args.alertmanager}/api/v2/alerts")
    evidence["alertmanager_alerts"] = am

    auth = grafana_auth(args.grafana_user, args.grafana_password)
    evidence["grafana_health"] = _get_json(f"{args.grafana}/api/health")
    evidence["grafana_datasources"] = _get_json(
        f"{args.grafana}/api/datasources", headers=auth
    )
    evidence["grafana_dashboards"] = _get_json(
        f"{args.grafana}/api/search?type=dash-db", headers=auth
    )

    evidence["loki_labels"] = _get_json(f"{args.loki}/loki/api/v1/labels")
    evidence["loki_sample"] = loki_query(
        args.loki, '{service="credit-scoring-api"}', limit=20
    )

    try:
        evidence["loki_ruler_rules"] = _get_json(f"{args.loki}/loki/api/v1/rules")
    except Exception as exc:  # noqa: BLE001
        evidence["loki_ruler_rules_error"] = str(exc)

    write_json(out, evidence)
    print(f"wrote {out}")
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    """Generate controlled synthetic HTTP load (no PII — zeros / schema defaults)."""
    # Synthetic schema-valid payload (same fields as tests.api.conftest; no real PII).
    sample = {
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
    # Fill remaining numeric features if API expects full schema via features dict.
    ok = 0
    fail = 0
    validation = 0
    for i in range(args.n):
        if i % 10 == 9:
            # Controlled validation error (422) — missing required fields.
            status, _ = _post_json(f"{args.api}/predict", {"SEX": 2})
            if status == 422:
                validation += 1
            else:
                fail += 1
        else:
            status, _ = _post_json(f"{args.api}/predict", sample)
            if 200 <= status < 300:
                ok += 1
            else:
                fail += 1
        time.sleep(args.sleep)
    summary = {
        "captured_at_utc": _utc(),
        "ok": ok,
        "validation_422": validation,
        "fail": fail,
        "n": args.n,
    }
    write_json(Path(args.output), summary)
    print(json.dumps(summary))
    return 0 if fail == 0 else 1


def cmd_inject_error_log(args: argparse.Namespace) -> int:
    """Trigger test-only e2e-log-probe service (Alloy → Loki).

    Production API has no /internal/e2e/log-error route.
    """
    status, body = _post_json(f"{args.probe.rstrip('/')}/error", {})
    write_json(
        Path(args.output),
        {
            "captured_at_utc": _utc(),
            "method": "e2e_log_probe_service",
            "marker": "BLOCK8_CONTROLLED_ERROR_LOG",
            "probe": args.probe,
            "http_status": status,
            "body": body,
        },
    )
    print(f"e2e log probe status={status}")
    return 0 if status == 200 else 1


def cmd_wait_alert(args: argparse.Namespace) -> int:
    deadline = time.time() + args.timeout
    history: list[dict[str, Any]] = []
    while time.time() < deadline:
        am = _get_json(f"{args.alertmanager}/api/v2/alerts")
        match = [
            a
            for a in am
            if a.get("labels", {}).get("alertname") == args.alertname
            and a.get("status", {}).get("state") == "active"
        ]
        snap = {
            "at": _utc(),
            "active_match": len(match),
            "alertnames": sorted({a.get("labels", {}).get("alertname") for a in am}),
        }
        history.append(snap)
        print(snap)
        if match:
            write_json(
                Path(args.output),
                {
                    "captured_at_utc": _utc(),
                    "alertname": args.alertname,
                    "status": "firing",
                    "alerts": match,
                    "history": history,
                },
            )
            return 0
        time.sleep(args.poll)
    write_json(
        Path(args.output),
        {
            "captured_at_utc": _utc(),
            "alertname": args.alertname,
            "status": "timeout",
            "history": history,
        },
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("snapshot")
    p.add_argument("--prometheus", default="http://127.0.0.1:9090")
    p.add_argument("--grafana", default="http://127.0.0.1:3000")
    p.add_argument("--loki", default="http://127.0.0.1:3100")
    p.add_argument("--alertmanager", default="http://127.0.0.1:9093")
    p.add_argument("--grafana-user", default="admin")
    p.add_argument("--grafana-password", default="admin")
    p.add_argument("--output", default="results/block8/observability_snapshot.json")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("load")
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--sleep", type=float, default=0.05)
    p.add_argument("--output", default="results/block8/load_summary.json")
    p.set_defaults(func=cmd_load)

    p = sub.add_parser("inject-error-log")
    p.add_argument("--probe", default="http://127.0.0.1:9109")
    p.add_argument("--output", default="results/block8/injected_error_log.json")
    p.set_defaults(func=cmd_inject_error_log)

    p = sub.add_parser("wait-alert")
    p.add_argument("--alertmanager", default="http://127.0.0.1:9093")
    p.add_argument("--alertname", required=True)
    p.add_argument("--timeout", type=float, default=180)
    p.add_argument("--poll", type=float, default=5)
    p.add_argument("--output", default="results/block8/alert_wait.json")
    p.set_defaults(func=cmd_wait_alert)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
