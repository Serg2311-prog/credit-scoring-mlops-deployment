"""Input checks for retraining — reuses Pandera schema from src.data.validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.data.validation import DataValidationError, validate_dataframe
from src.retraining.config import load_retraining_config
from src.retraining.exceptions import DataValidationFailed
from src.schema import RAW_FEATURE_COLUMNS, TARGET_COLUMN, detect_target


def read_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise DataValidationFailed(f"Input file not found: {path}")
    if path.stat().st_size == 0:
        raise DataValidationFailed(f"Input file is empty: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix == ".parquet":
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        raise DataValidationFailed(f"Failed to read {path}: {exc}") from exc
    if frame is None or len(frame) == 0:
        raise DataValidationFailed(f"Dataset is empty after read: {path}")
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def validate_retraining_frame(
    frame: pd.DataFrame,
    *,
    target_hint: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate schema, target presence, class balance, and minimum size."""
    cfg = cfg or load_retraining_config()
    rt = cfg.get("retraining", {})
    min_rows = int(rt.get("min_rows", 40))
    min_pos = int(rt.get("min_positives", 5))
    min_neg = int(rt.get("min_negatives", 5))

    if frame is None or len(frame) == 0:
        raise DataValidationFailed("Dataset is empty")

    preferred = target_hint or TARGET_COLUMN
    try:
        target = detect_target(frame.columns, preferred=preferred)
    except ValueError as exc:
        raise DataValidationFailed(
            "Target column is missing; cannot train without labels"
        ) from exc

    missing_features = [c for c in RAW_FEATURE_COLUMNS if c not in frame.columns]
    if missing_features:
        raise DataValidationFailed(
            "Missing required feature columns: " + ", ".join(missing_features)
        )

    # Drop ID if present — never a model feature.
    working = frame.copy()
    if "ID" in working.columns:
        working = working.drop(columns=["ID"])

    try:
        validated = validate_dataframe(working, target_column=target)
    except DataValidationError as exc:
        raise DataValidationFailed(str(exc)) from exc

    y = validated[target].astype(int)
    n = int(len(validated))
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    n_unique = int(y.nunique())

    if n < min_rows:
        raise DataValidationFailed(f"Insufficient rows: {n} < min_rows={min_rows}")
    if n_unique < 2:
        raise DataValidationFailed(
            "Target has a single class; stratified split / ROC-AUC undefined"
        )
    if n_pos < min_pos or n_neg < min_neg:
        raise DataValidationFailed(
            f"Class imbalance too extreme for training "
            f"(pos={n_pos}, neg={n_neg}; need pos>={min_pos}, neg>={min_neg})"
        )

    # Ensure target not mixed into feature list for downstream steps.
    feature_cols = [c for c in RAW_FEATURE_COLUMNS if c != target]
    return {
        "status": "ok",
        "target": target,
        "rows": n,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "feature_columns": feature_cols,
        "target_excluded_from_features": True,
        "min_rows": min_rows,
        "validated_frame": validated,
    }


def check_input_data(
    path: Path,
    *,
    target_hint: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    frame = read_table(path)
    result = validate_retraining_frame(frame, target_hint=target_hint, cfg=cfg)
    # Do not serialize the DataFrame into JSON reports.
    payload = {k: v for k, v in result.items() if k != "validated_frame"}
    payload["input_path"] = str(path)
    payload["validated_frame"] = result["validated_frame"]
    return payload
