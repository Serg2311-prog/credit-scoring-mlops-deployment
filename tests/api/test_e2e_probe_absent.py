"""Production API must not expose Block-8 E2E log probe routes."""

from __future__ import annotations

from src.api.main import app
from src.api.settings import Settings


def test_settings_have_no_e2e_log_probe_flag():
    assert not hasattr(Settings, "enable_e2e_log_probe")
    fields = getattr(Settings, "model_fields", {})
    assert "enable_e2e_log_probe" not in fields


def test_app_routes_exclude_internal_e2e_log_error():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/internal/e2e/log-error" not in paths
