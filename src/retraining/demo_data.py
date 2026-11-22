"""Synthetic demo input for Stage 7 (no real credit/PII rows)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT, dump_json
from src.data.synthetic import make_synthetic_frame
from src.retraining.config import artifacts_root

DEFAULT_DEMO_INPUT = artifacts_root() / "demo_input" / "retrain_input.csv"


def demo_input_path() -> Path:
    return DEFAULT_DEMO_INPUT


def prepare_demo_input(
    *,
    output_path: Path | None = None,
    rows: int = 120,
    seed: int = 7,
) -> dict[str, Any]:
    """
    Write a reproducible synthetic CSV for DAG/CLI demos.

    Does not touch production models/registry. File is under artifacts/
    (gitignored) — never commit real credit data.
    """
    path = Path(output_path) if output_path else demo_input_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = make_synthetic_frame(rows, seed=seed)
    frame.to_csv(path, index=False)
    try:
        relative = str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        relative = None
    meta = {
        "path": str(path),
        "rows": int(len(frame)),
        "seed": int(seed),
        "synthetic_only": True,
        "no_real_pii": True,
        "relative_to_project": relative,
        "note": (
            "Use as RETRAIN_INPUT_PATH / --input for Stage 7 demos. "
            "Missing file must fail DAG check_input_data."
        ),
    }
    dump_json(path.parent / "demo_input_meta.json", meta)
    return meta
