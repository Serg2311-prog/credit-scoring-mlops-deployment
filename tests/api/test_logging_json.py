"""Structured logging must expose observability fields without PII bodies."""

from __future__ import annotations

import json
import logging

from src.api.logging_config import JsonFormatter


def test_json_formatter_includes_service_level_request_id():
    record = logging.LogRecord(
        name="src.api",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-test-1"
    record.endpoint = "/predict"
    record.status_code = 200
    payload = json.loads(JsonFormatter().format(record))
    assert payload["service"] == "credit-scoring-api"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-test-1"
    assert "LIMIT_BAL" not in payload
    assert "password" not in payload
