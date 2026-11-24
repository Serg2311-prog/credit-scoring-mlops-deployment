"""Detect new/changed retraining inputs via content fingerprint (not force_retrain)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import dump_json, load_json
from src.retraining.config import artifacts_root


def input_state_path() -> Path:
    return artifacts_root() / "state" / "input_fingerprint.json"


def fingerprint_input(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "sha256": digest.hexdigest(),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9))),
    }


def load_input_baseline(state_file: Path | None = None) -> dict[str, Any] | None:
    path = Path(state_file) if state_file else input_state_path()
    if not path.is_file():
        return None
    try:
        return load_json(path)
    except (OSError, ValueError):
        return None


def save_input_baseline(
    path: Path,
    *,
    state_file: Path | None = None,
    note: str = "baseline",
) -> dict[str, Any]:
    fp = fingerprint_input(path)
    payload = {
        **fp,
        "saved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": note,
    }
    out = Path(state_file) if state_file else input_state_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    dump_json(out, payload)
    return payload


def compare_input_to_baseline(
    path: Path,
    *,
    state_file: Path | None = None,
) -> dict[str, Any]:
    """
    Compare current input fingerprint to last saved baseline.

    Returns status:
    - ``triggered`` — content hash differs from baseline (new_data)
    - ``skipped`` — hash matches baseline
    - ``unavailable`` — baseline missing (must call save_input_baseline first)
    """
    current = fingerprint_input(path)
    baseline = load_input_baseline(state_file)
    if baseline is None:
        return {
            "status": "unavailable",
            "triggered": False,
            "reason": "new_data",
            "message": (
                "No input fingerprint baseline; "
                "run prepare-demo-input then baseline-input-state "
                "(or save_input_baseline) before new_data trigger"
            ),
            "current": current,
            "baseline": None,
        }
    changed = str(baseline.get("sha256")) != str(current.get("sha256"))
    if changed:
        return {
            "status": "triggered",
            "triggered": True,
            "reason": "new_data",
            "message": "Input fingerprint changed relative to baseline",
            "current": current,
            "baseline": {
                "sha256": baseline.get("sha256"),
                "size_bytes": baseline.get("size_bytes"),
                "saved_at_utc": baseline.get("saved_at_utc"),
            },
        }
    return {
        "status": "skipped",
        "triggered": False,
        "reason": "new_data",
        "message": "Input fingerprint unchanged — no new data",
        "current": current,
        "baseline": {
            "sha256": baseline.get("sha256"),
            "size_bytes": baseline.get("size_bytes"),
            "saved_at_utc": baseline.get("saved_at_utc"),
        },
    }
