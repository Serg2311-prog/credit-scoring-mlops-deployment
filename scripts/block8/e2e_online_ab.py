"""Online A/B routing E2E against an isolated compose API (synthetic traffic)."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.monitoring.ab_testing import assign_ab_group
from tests.api.conftest import sample_client_payload


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(
    url: str, payload: dict, headers: dict | None = None
) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return int(exc.code), parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--n-ids", type=int, default=1000)
    parser.add_argument("--n-http", type=int, default=120)
    parser.add_argument("--share", type=float, default=0.30)
    parser.add_argument("--salt", default="block81-online-ab-e2e")
    parser.add_argument("--output", default="results/block8/online_ab_evidence.json")
    args = parser.parse_args()

    info = _get_json(f"{args.api.rstrip('/')}/model/info")
    ready = _get_json(f"{args.api.rstrip('/')}/health/ready")

    # Offline deterministic assignment check (no HTTP).
    ids = [f"ab-unit-{i}" for i in range(args.n_ids)]
    groups = [
        assign_ab_group(uid, challenger_share=args.share, salt=args.salt) for uid in ids
    ]
    counts = Counter(groups)
    share = counts["challenger"] / len(ids)
    # Reproducibility
    groups2 = [
        assign_ab_group(uid, challenger_share=args.share, salt=args.salt) for uid in ids
    ]
    stable = groups == groups2

    # HTTP inference with request_id as assignment key (unit_id_from_record).
    sample = sample_client_payload()
    http_versions: Counter[str] = Counter()
    http_groups: Counter[str] = Counter()
    errors = 0
    for i in range(args.n_http):
        uid = f"http-ab-{i}"
        status, body = _post_json(
            f"{args.api.rstrip('/')}/predict",
            sample,
            headers={"X-Request-ID": uid},
        )
        if status != 200:
            errors += 1
            continue
        version = str(body.get("model_version", ""))
        http_versions[version] += 1
        expected = assign_ab_group(uid, challenger_share=args.share, salt=args.salt)
        http_groups[expected] += 1
        time.sleep(0.01)

    # Metrics endpoint should expose AB counter when enabled.
    metrics_text = (
        urllib.request.urlopen(f"{args.api.rstrip('/')}/metrics", timeout=10)
        .read()
        .decode("utf-8", errors="replace")
    )
    has_ab_metric = "ml_ab_experiment_samples" in metrics_text

    evidence = {
        "captured_at_utc": _utc(),
        "mode": "online_routing_verification_synthetic_http",
        "not_real_clients": True,
        "auto_promote": False,
        "model_info": info,
        "ready": ready,
        "assignment": {
            "n_ids": args.n_ids,
            "challenger_share_configured": args.share,
            "challenger_share_observed": share,
            "counts": dict(counts),
            "reproducible": stable,
            "within_tolerance": abs(share - args.share) <= 0.05,
        },
        "http": {
            "n_requests": args.n_http,
            "errors": errors,
            "model_versions": dict(http_versions),
            "expected_groups": dict(http_groups),
            "both_branches_seen": len(http_versions) >= 2,
        },
        "prometheus": {"ml_ab_experiment_samples_present": has_ab_metric},
        "challenger_variant": "credit_scoring_nn.quant.onnx (experimental INT8)",
        "champion_variant": "credit_scoring_nn.onnx (FP32 production champion bytes)",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps({"wrote": str(out), "share": share, "versions": dict(http_versions)})
    )
    ok = (
        stable
        and abs(share - args.share) <= 0.05
        and errors == 0
        and len(http_versions) >= 1
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
