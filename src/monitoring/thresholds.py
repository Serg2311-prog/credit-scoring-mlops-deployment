"""Load Stage 6 monitoring thresholds from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.config import PROJECT_ROOT

DEFAULT_THRESHOLDS_PATH = (
    PROJECT_ROOT / "configs" / "monitoring" / "stage6_thresholds.yaml"
)


def load_stage6_thresholds(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_THRESHOLDS_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"Stage 6 thresholds not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("stage6_thresholds.yaml must contain a mapping")
    return payload
