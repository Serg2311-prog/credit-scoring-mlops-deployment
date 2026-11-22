"""Stage 7 retraining configuration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from src.config import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "retraining" / "stage7.yaml"


def load_retraining_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"Stage 7 config not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("stage7.yaml must contain a mapping")
    return deepcopy(payload)


def artifacts_root(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_retraining_config()
    relative = cfg.get("artifacts", {}).get("root", "artifacts/retraining")
    path = PROJECT_ROOT / relative
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir(
    run_id: str, *, dry_run: bool = False, cfg: dict[str, Any] | None = None
) -> Path:
    root = artifacts_root(cfg)
    folder = root / ("dry_run" if dry_run else "runs") / run_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder
