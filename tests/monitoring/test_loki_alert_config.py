"""Static checks for Loki ruler + Alloy label cardinality."""

from __future__ import annotations

from src.config import PROJECT_ROOT


def test_loki_ruler_has_log_based_alert():
    rules = (
        PROJECT_ROOT / "monitoring" / "loki" / "rules" / "fake" / "rules.yml"
    ).read_text(encoding="utf-8")
    assert "APIErrorLogsDetected" in rules
    assert "alert_source: loki" in rules
    assert "count_over_time" in rules
    assert 'level="ERROR"' in rules


def test_alloy_configs_omit_request_id_stream_label():
    for name in ("config.alloy", "config.e2e.alloy"):
        text = (PROJECT_ROOT / "monitoring" / "alloy" / name).read_text(
            encoding="utf-8"
        )
        # Only stage.labels values must stay low-cardinality.
        labels_blocks = []
        parts = text.split("stage.labels")
        for part in parts[1:]:
            block = part.split("}", 1)[0]
            labels_blocks.append(block)
        assert labels_blocks, name
        for block in labels_blocks:
            assert "request_id" not in block
            assert "level" in block
            assert "service" in block


def test_production_compose_has_no_e2e_log_probe_service():
    base = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    obs = (PROJECT_ROOT / "docker-compose.observability.yml").read_text(
        encoding="utf-8"
    )
    assert "e2e-log-probe" not in base
    assert "e2e-log-probe" not in obs
    e2e = (PROJECT_ROOT / "docker-compose.observability.e2e.yml").read_text(
        encoding="utf-8"
    )
    assert "e2e-log-probe" in e2e
