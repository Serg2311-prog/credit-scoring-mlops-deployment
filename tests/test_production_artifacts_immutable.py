"""Regression: pytest helpers must not mutate production models/ or dvc.lock."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.config import PROJECT_ROOT
from src.monitoring.ab_testing import write_model_registry


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_write_model_registry_tmp_path_leaves_production_untouched(tmp_path: Path):
    production = PROJECT_ROOT / "models" / "model_registry.json"
    before = _sha256(production)
    assert before is not None
    dest = tmp_path / "registry.json"
    write_model_registry({"note_test": True}, registry_path=dest)
    assert dest.is_file()
    assert _sha256(production) == before
    # Ensure the production file was not appended with the test marker.
    text = production.read_text(encoding="utf-8")
    assert "note_test" not in text


def test_repo_dvc_lock_has_no_trailing_whitespace_on_cmd_lines():
    """Guardrail: committed lock must stay clean for git diff --check."""
    lock = PROJECT_ROOT / "dvc.lock"
    assert lock.is_file()
    for i, line in enumerate(lock.read_text(encoding="utf-8").splitlines(), start=1):
        assert line == line.rstrip(" \t"), f"trailing whitespace on dvc.lock line {i}"
