"""Demo/A/B helpers must never mutate production models/model_registry.json."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import PROJECT_ROOT
from src.monitoring.ab_testing import (
    production_model_registry_path,
    write_model_registry,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_write_model_registry_defaults_to_artifacts(tmp_path: Path, monkeypatch):
    production = production_model_registry_path()
    before = _sha(production)
    # Force monitoring_dir into tmp via monkeypatch of reports.monitoring_dir
    import src.monitoring.ab_testing as ab_mod
    import src.monitoring.reports as reports

    monkeypatch.setattr(reports, "monitoring_dir", lambda: tmp_path)
    monkeypatch.setattr(ab_mod, "monitoring_dir", lambda: tmp_path)
    path = write_model_registry({"demo": True})
    assert path.parent == tmp_path
    assert path.is_file()
    assert _sha(production) == before


def test_write_model_registry_refuses_production_without_flag():
    production = production_model_registry_path()
    before = _sha(production)
    with pytest.raises(PermissionError, match="Refusing to write production"):
        write_model_registry({"hack": True}, registry_path=production)
    assert _sha(production) == before


def test_demo_cli_twice_leaves_production_registry_unchanged():
    production = production_model_registry_path()
    before = _sha(production)
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, "-m", "src.monitoring.cli", "demo"],
            cwd=str(PROJECT_ROOT),
            check=False,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
        assert _sha(production) == before
    after = _sha(production)
    assert after == before
