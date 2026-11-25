"""Aggregated drift metrics exporter — no invented zeros."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.monitoring.prometheus_export import (
    MonitoringArtifactsUnavailable,
    collect_monitoring_gauges,
    render_prometheus_text,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_collect_gauges_from_valid_artifacts(tmp_path: Path):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write(
        tmp_path / "data_drift" / "demo_data_drift_shift.json",
        {
            "generated_at_utc": now,
            "drift_share": 0.375,
            "data_drift_detected": True,
        },
    )
    _write(
        tmp_path / "concept_drift" / "demo_concept_signal.json",
        {
            "generated_at_utc": now,
            "degradation_signal": True,
            "current": {"metrics": {"roc_auc": 0.7, "pr_auc": 0.65}},
        },
    )
    gauges = collect_monitoring_gauges(root=tmp_path)
    assert gauges["ml_data_drift_share"] == 0.375
    assert gauges["ml_data_drift_detected"] == 1.0
    assert gauges["ml_model_roc_auc"] == 0.7
    text = render_prometheus_text(gauges)
    assert "ml_data_drift_share 0.375" in text


def test_missing_artifacts_raise():
    with pytest.raises(MonitoringArtifactsUnavailable):
        collect_monitoring_gauges(root=Path("definitely/missing/path"))


def test_corrupt_artifacts_raise(tmp_path: Path):
    path = tmp_path / "data_drift" / "demo_data_drift_shift.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")
    (tmp_path / "concept_drift").mkdir()
    (tmp_path / "concept_drift" / "x.json").write_text("{}", encoding="utf-8")
    with pytest.raises(MonitoringArtifactsUnavailable):
        collect_monitoring_gauges(root=tmp_path)
