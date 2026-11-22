"""Structured Stage 6 report helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT, dump_json


def monitoring_dir() -> Path:
    path = PROJECT_ROOT / "artifacts" / "monitoring"
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_report(
    name: str,
    payload: dict[str, Any],
    *,
    subdirectory: str | None = None,
) -> Path:
    root = monitoring_dir()
    if subdirectory:
        root = root / subdirectory
        root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.json"
    envelope = {
        "report_name": name,
        "generated_at_utc": utc_now_iso(),
        **payload,
    }
    dump_json(path, envelope)
    return path
