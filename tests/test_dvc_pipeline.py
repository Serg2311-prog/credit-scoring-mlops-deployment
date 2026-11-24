"""DVC pipeline presence and local repro smoke (synthetic data only).

``dvc repro`` must run in an isolated workspace — never rewrite repo ``dvc.lock``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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


def _dvc_env(ws: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ws)
    env["DVC_ANALYTICS"] = "false"
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    scripts = ROOT / ".venv" / "Scripts"
    bin_dir = ROOT / ".venv" / "bin"
    prepend = scripts if scripts.is_dir() else bin_dir
    if prepend.is_dir():
        env["PATH"] = str(prepend) + os.pathsep + env["PATH"]
    return env


def _dvc_cmd(*args: str) -> list[str]:
    return [sys.executable, "-m", "dvc", *args]


def _build_isolated_dvc_workspace(tmp_path: Path) -> Path:
    """Copy pipeline definition + code into tmp; local remote under tmp only."""
    ws = tmp_path / "dvc_ws"
    remote = tmp_path / "dvc_remote"
    remote.mkdir()
    ws.mkdir()
    shutil.copy2(ROOT / "dvc.yaml", ws / "dvc.yaml")
    shutil.copytree(ROOT / "scripts" / "dvc", ws / "scripts" / "dvc")
    shutil.copytree(ROOT / "src", ws / "src")
    (ws / "data" / "dvc_tracked").mkdir(parents=True)
    (ws / ".dvc").mkdir()
    (ws / ".dvc" / "config").write_text(
        "\n".join(
            [
                "[core]",
                "    remote = localremote",
                "    autostage = false",
                "['remote \"localremote\"']",
                f"    url = {remote.resolve().as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return ws


@pytest.mark.skipif(
    shutil.which("dvc") is None
    and not (ROOT / ".venv" / "Scripts" / "dvc.exe").exists(),
    reason="dvc not installed",
)
def test_dvc_repro_and_pull_roundtrip(tmp_path: Path):
    repo_lock = ROOT / "dvc.lock"
    lock_before = repo_lock.read_bytes()
    ws = _build_isolated_dvc_workspace(tmp_path)
    env = _dvc_env(ws)

    # Minimal git repo — modern DVC repro still expects SCM even with --no-scm init.
    git_init = subprocess.run(
        ["git", "init"],
        cwd=ws,
        capture_output=True,
        text=True,
        check=False,
    )
    assert git_init.returncode == 0, git_init.stdout + "\n" + git_init.stderr
    init = subprocess.run(
        _dvc_cmd("init", "--force"),
        cwd=ws,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert init.returncode == 0, init.stdout + "\n" + init.stderr
    # Re-apply isolated remote after init (init may rewrite config).
    remote = tmp_path / "dvc_remote"
    (ws / ".dvc" / "config").write_text(
        "\n".join(
            [
                "[core]",
                "    remote = localremote",
                "    autostage = false",
                "['remote \"localremote\"']",
                f"    url = {remote.resolve().as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    repro = subprocess.run(
        _dvc_cmd("repro", "--force"),
        cwd=ws,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert repro.returncode == 0, repro.stdout + "\n" + repro.stderr

    train = ws / "data" / "dvc_tracked" / "train_demo.csv"
    meta = ws / "data" / "dvc_tracked" / "demo_meta.json"
    assert train.is_file()
    assert meta.is_file()
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["synthetic_only"] is True
    assert payload["rows_train"] > 0
    # Lock may be rewritten inside the workspace only.
    assert (ws / "dvc.lock").is_file()
    ws_lock = yaml.safe_load((ws / "dvc.lock").read_text(encoding="utf-8"))
    assert "stages" in ws_lock
    assert set(ws_lock["stages"]) >= {
        "generate_demo",
        "prepare_demo",
        "validate_ml_ready",
    }

    push = subprocess.run(
        _dvc_cmd("push"),
        cwd=ws,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert push.returncode == 0, push.stdout + "\n" + push.stderr

    for name in (
        "raw_demo.csv",
        "train_demo.csv",
        "test_demo.csv",
        "demo_meta.json",
        "train_smoke_metrics.json",
    ):
        path = ws / "data" / "dvc_tracked" / name
        if path.exists():
            path.unlink()

    pull = subprocess.run(
        _dvc_cmd("pull"),
        cwd=ws,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert pull.returncode == 0, pull.stdout + "\n" + pull.stderr
    assert train.is_file()
    assert meta.is_file()

    # Repo lock must be byte-identical (no trailing-whitespace rewrite in tree).
    assert repo_lock.read_bytes() == lock_before
