"""Decision-layer Airflow trigger checks using real Block 8 monitoring artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.retraining.config import load_retraining_config
from src.retraining.triggers import evaluate_triggers


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts-root",
        default="artifacts/monitoring",
    )
    parser.add_argument(
        "--config",
        default="configs/retraining/stage7.yaml",
    )
    parser.add_argument(
        "--output",
        default="results/block8/airflow_trigger_decisions.json",
    )
    args = parser.parse_args()
    root = Path(args.artifacts_root)
    cfg = load_retraining_config(Path(args.config))

    drift_none = _load(root / "data_drift" / "demo_data_drift_none.json")
    drift_shift = _load(root / "data_drift" / "demo_data_drift_shift.json")
    quality = _load(root / "concept_drift" / "demo_concept_signal.json")

    cases = {}

    stable = evaluate_triggers(
        modes=["data_drift", "quality_drop"],
        drift_report=drift_none,
        quality_report={
            **quality,
            "degradation_signal": False,
            "dropped_metrics": [],
        },
        cfg=cfg,
    )
    cases["stable_baseline"] = {
        "status": stable.get("status"),
        "fired": stable.get("fired_modes") or stable.get("fired"),
        "expect": "skipped",
    }

    drift = evaluate_triggers(
        modes=["data_drift"],
        drift_report=drift_shift,
        cfg=cfg,
    )
    cases["detected_drift"] = {
        "status": drift.get("status"),
        "fired": drift.get("fired_modes") or drift.get("fired"),
        "expect": "triggered",
    }

    degr = evaluate_triggers(
        modes=["quality_drop"],
        quality_report=quality,
        cfg=cfg,
    )
    cases["performance_degradation"] = {
        "status": degr.get("status"),
        "fired": degr.get("fired_modes") or degr.get("fired"),
        "expect": "triggered",
        "auto_promote": False,
    }

    invalid = evaluate_triggers(
        modes=["data_drift"],
        drift_report={
            "status": "insufficient_data",
            "message": "controlled corrupt/incomplete artifact",
        },
        cfg=cfg,
    )
    cases["invalid_artifact"] = {
        "status": invalid.get("status"),
        "fired": invalid.get("fired_modes") or invalid.get("fired"),
        "expect": "unavailable",
    }

    evidence = {
        "captured_at_utc": _utc(),
        "scope": "decision_layer_only",
        "full_retrain_executed": False,
        "auto_promote": False,
        "cases": cases,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))

    ok = (
        cases["stable_baseline"]["status"] == "skipped"
        and cases["detected_drift"]["status"] == "triggered"
        and cases["performance_degradation"]["status"] == "triggered"
        and cases["invalid_artifact"]["status"] == "unavailable"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
