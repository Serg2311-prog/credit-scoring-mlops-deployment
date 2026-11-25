"""Export aggregated monitoring artifacts as Prometheus text (no PII)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.monitoring.reports import monitoring_dir


class MonitoringArtifactsUnavailable(Exception):
    """Raised when required monitoring JSON is missing or unusable."""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MonitoringArtifactsUnavailable(f"missing artifact: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MonitoringArtifactsUnavailable(f"corrupt artifact: {path}") from exc
    if not isinstance(data, dict):
        raise MonitoringArtifactsUnavailable(f"artifact not an object: {path}")
    return data


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        # Accept ISO-8601 with optional Z
        from datetime import datetime

        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).timestamp()
    except ValueError:
        return None


def collect_monitoring_gauges(
    *,
    root: Path | None = None,
    max_age_seconds: float = 7 * 24 * 3600,
) -> dict[str, float]:
    """Read latest Stage-6 style artifacts into flat gauges.

    Missing/stale/corrupt files raise ``MonitoringArtifactsUnavailable`` —
    callers must not invent zeros.
    """
    root = root or monitoring_dir()
    drift_path = root / "data_drift" / "demo_data_drift_shift.json"
    if not drift_path.is_file():
        # Prefer any data_drift JSON except *_none if shift missing
        candidates = (
            sorted((root / "data_drift").glob("*.json"))
            if (root / "data_drift").is_dir()
            else []
        )
        drift_path = next(
            (p for p in candidates if "none" not in p.name),
            candidates[0] if candidates else drift_path,
        )
    concept_path = root / "concept_drift" / "demo_concept_signal.json"
    if not concept_path.is_file():
        concept_candidates = (
            sorted((root / "concept_drift").glob("*.json"))
            if (root / "concept_drift").is_dir()
            else []
        )
        concept_path = concept_candidates[0] if concept_candidates else concept_path

    drift = _load_json(drift_path)
    concept = _load_json(concept_path)

    now = time.time()
    for label, payload in (("drift", drift), ("concept", concept)):
        ts = _parse_ts(payload.get("generated_at_utc") or payload.get("created_at_utc"))
        if ts is None:
            raise MonitoringArtifactsUnavailable(
                f"{label} artifact missing generated_at_utc"
            )
        if now - ts > max_age_seconds:
            raise MonitoringArtifactsUnavailable(
                f"{label} artifact stale age_s={now - ts:.0f}"
            )

    share = drift.get("drift_share")
    detected = drift.get("data_drift_detected")
    if share is None or detected is None:
        raise MonitoringArtifactsUnavailable("drift artifact missing share/detected")

    current_block = concept.get("current") or {}
    metrics_block = (
        current_block.get("metrics")
        or concept.get("current_metrics")
        or concept.get("metrics")
        or {}
    )
    roc = metrics_block.get("roc_auc") if isinstance(metrics_block, dict) else None
    pr = metrics_block.get("pr_auc") if isinstance(metrics_block, dict) else None
    degradation = concept.get("degradation_signal")
    if degradation is None:
        raise MonitoringArtifactsUnavailable(
            "concept artifact missing degradation_signal"
        )

    gauges = {
        "ml_data_drift_share": float(share),
        "ml_data_drift_detected": 1.0 if detected else 0.0,
        "ml_performance_degradation_signal": 1.0 if degradation else 0.0,
        "ml_monitoring_last_success_unixtime": float(
            _parse_ts(drift.get("generated_at_utc")) or now
        ),
    }
    if roc is not None:
        gauges["ml_model_roc_auc"] = float(roc)
    if pr is not None:
        gauges["ml_model_pr_auc"] = float(pr)
    return gauges


def render_prometheus_text(gauges: dict[str, float]) -> str:
    help_map = {
        "ml_data_drift_share": "Share of drifted features from last Evidently run",
        "ml_data_drift_detected": "1 if data drift detected else 0",
        "ml_model_roc_auc": "ROC-AUC from last labeled quality check",
        "ml_model_pr_auc": "PR-AUC from last labeled quality check",
        "ml_performance_degradation_signal": "1 if degradation signal else 0",
        "ml_monitoring_last_success_unixtime": (
            "Unix time of last successful export source"
        ),
    }
    out: list[str] = []
    for name, value in sorted(gauges.items()):
        out.append(f"# HELP {name} {help_map.get(name, name)}")
        out.append(f"# TYPE {name} gauge")
        out.append(f"{name} {value}")
    return "\n".join(out) + "\n"
