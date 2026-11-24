"""DVC pipeline presence and local repro smoke (synthetic data only)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_dvc_project_files_exist():
    assert (ROOT / "dvc.yaml").is_file()
    assert (ROOT / ".dvc" / "config").is_file()
    assert (ROOT / "scripts" / "dvc" / "generate_demo_dataset.py").is_file()
    assert (ROOT / "scripts" / "dvc" / "prepare_demo_dataset.py").is_file()
    cfg = (ROOT / ".dvc" / "config").read_text(encoding="utf-8")
    assert "localremote" in cfg
    assert ".dvc_remote" in cfg


def test_dvc_yaml_stages():
    payload = yaml.safe_load((ROOT / "dvc.yaml").read_text(encoding="utf-8"))
    stages = payload["stages"]
    assert "generate_demo" in stages
    assert "prepare_demo" in stages
    assert "validate_ml_ready" in stages
    assert (ROOT / "dvc.lock").is_file()


def _dvc_env() -> dict[str, str]:
    import os
    import sys

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["DVC_ANALYTICS"] = "false"
    scripts = ROOT / ".venv" / "Scripts"
    bin_dir = ROOT / ".venv" / "bin"
    prepend = scripts if scripts.is_dir() else bin_dir
    if prepend.is_dir():
        env["PATH"] = str(prepend) + os.pathsep + env.get("PATH", "")
    # Prefer the same interpreter running pytest.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    return env


def _dvc_cmd(*args: str) -> list[str]:
    import sys

    return [sys.executable, "-m", "dvc", *args]


@pytest.mark.skipif(
    shutil.which("dvc") is None
    and not (ROOT / ".venv" / "Scripts" / "dvc.exe").exists(),
    reason="dvc not installed",
)
def test_dvc_repro_and_pull_roundtrip(tmp_path: Path):
    env = _dvc_env()

    repro = subprocess.run(
        _dvc_cmd("repro", "--force"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert repro.returncode == 0, repro.stdout + "\n" + repro.stderr

    train = ROOT / "data" / "dvc_tracked" / "train_demo.csv"
    meta = ROOT / "data" / "dvc_tracked" / "demo_meta.json"
    assert train.is_file()
    assert meta.is_file()
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["synthetic_only"] is True
    assert payload["rows_train"] > 0

    push = subprocess.run(
        _dvc_cmd("push"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert push.returncode == 0, push.stdout + "\n" + push.stderr

    # Simulate clean checkout: remove outs, then pull from local remote.
    for name in (
        "raw_demo.csv",
        "train_demo.csv",
        "test_demo.csv",
        "demo_meta.json",
    ):
        path = ROOT / "data" / "dvc_tracked" / name
        if path.exists():
            path.unlink()

    pull = subprocess.run(
        _dvc_cmd("pull"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert pull.returncode == 0, pull.stdout + "\n" + pull.stderr
    assert train.is_file()
    assert meta.is_file()
