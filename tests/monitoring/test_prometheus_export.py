"""Aggregated drift metrics exporter — no invented zeros."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.monitoring.prometheus_export import (
    MonitoringArtifactsUnavailable,
    collect_monitoring_gauges,
    render_prometheus_text,
    resolve_monitoring_export,
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
    text = render_prometheus_text(gauges, status="valid")
    assert "ml_monitoring_artifact_status 1.0" in text
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
    with pytest.raises(MonitoringArtifactsUnavailable) as exc:
        collect_monitoring_gauges(root=tmp_path)
    assert exc.value.status == "invalid"


def test_resolve_missing_is_unavailable_without_fake_zeros(tmp_path: Path):
    export = resolve_monitoring_export(root=tmp_path)
    assert export.status == "unavailable"
    assert export.gauges == {}
    text = render_prometheus_text(
        export.gauges, status=export.status, detail=export.detail
    )
    assert "ml_monitoring_artifact_status 0.0" in text
    assert "ml_data_drift_share" not in text
    assert "ml_data_drift_detected" not in text


def test_resolve_stale_status(tmp_path: Path):
    _write(
        tmp_path / "data_drift" / "demo_data_drift_shift.json",
        {
            "generated_at_utc": "2000-01-01T00:00:00+00:00",
            "drift_share": 0.1,
            "data_drift_detected": False,
        },
    )
    _write(
        tmp_path / "concept_drift" / "demo_concept_signal.json",
        {
            "generated_at_utc": "2000-01-01T00:00:00+00:00",
            "degradation_signal": False,
            "current": {"metrics": {"roc_auc": 0.7}},
        },
    )
    export = resolve_monitoring_export(root=tmp_path, max_age_seconds=3600)
    assert export.status == "stale"
    text = render_prometheus_text(export.gauges, status=export.status)
    assert "ml_monitoring_artifact_status 2.0" in text
    assert "ml_data_drift_share" not in text


def test_zero_drift_share_is_allowed_when_valid(tmp_path: Path):
    """Real zero from Evidently is OK; invented zeros when missing are not."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write(
        tmp_path / "data_drift" / "demo_data_drift_shift.json",
        {
            "generated_at_utc": now,
            "drift_share": 0.0,
            "data_drift_detected": False,
        },
    )
    _write(
        tmp_path / "concept_drift" / "demo_concept_signal.json",
        {
            "generated_at_utc": now,
            "degradation_signal": False,
            "current": {"metrics": {"roc_auc": 0.77}},
        },
    )
    export = resolve_monitoring_export(root=tmp_path)
    assert export.status == "valid"
    assert export.gauges["ml_data_drift_share"] == 0.0
    text = render_prometheus_text(export.gauges, status="valid")
    assert "ml_data_drift_share 0.0" in text
