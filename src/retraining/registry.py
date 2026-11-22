"""Atomic model registry updates — never silently promote champion."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT, load_json
from src.retraining.exceptions import RegistryError

DEFAULT_REGISTRY = PROJECT_ROOT / "models" / "model_registry.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception as exc:  # noqa: BLE001
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass
        raise RegistryError(f"Failed atomic registry write: {exc}") from exc


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or DEFAULT_REGISTRY
    if not registry_path.is_file():
        return {
            "production_champion": "mlp-onnx-fp32-v1",
            "challenger_candidate": None,
            "auto_promote": False,
            "candidates": [],
        }
    try:
        return load_json(registry_path)
    except (OSError, ValueError) as exc:
        raise RegistryError(f"Cannot read registry {registry_path}: {exc}") from exc


def register_candidate(
    candidate: dict[str, Any],
    *,
    registry_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Append candidate metadata. Does **not** change production_champion.

    dry_run writes only a sidecar JSON under the candidate run dir expectation
    when registry_path points to a dry-run location; if dry_run=True and path is
    default production path, registration is skipped and a copy is returned.
    """
    path = registry_path or DEFAULT_REGISTRY
    if dry_run and path.resolve() == DEFAULT_REGISTRY.resolve():
        return {
            "status": "dry_run_skipped_production_registry",
            "auto_promote": False,
            "candidate": candidate,
            "registry_path": str(path),
        }

    current = load_registry(path)
    champion = current.get("production_champion")
    candidates = list(current.get("candidates") or [])
    entry = {
        **candidate,
        "registered_at_utc": utc_now_iso(),
        "promoted": False,
        "auto_promote": False,
    }
    # Replace same version if re-run (idempotent).
    version = entry.get("version")
    candidates = [c for c in candidates if c.get("version") != version]
    candidates.append(entry)

    updated = {
        **current,
        "updated_at_utc": utc_now_iso(),
        "production_champion": champion,
        "challenger_candidate": version,
        "latest_candidate": entry,
        "candidates": candidates[-50:],  # keep tail bounded
        "auto_promote": False,
        "notes": current.get(
            "notes",
            "Promotion is manual. Never overwrite champion from retraining DAG.",
        ),
    }
    # Hard guard: champion must remain unchanged by this function.
    if updated["production_champion"] != champion:
        raise RegistryError("Refusing to modify production_champion during register")

    _atomic_write_json(path, updated)
    return {
        "status": "registered",
        "registry_path": str(path),
        "production_champion": champion,
        "challenger_candidate": version,
        "auto_promote": False,
        "candidate": entry,
    }
