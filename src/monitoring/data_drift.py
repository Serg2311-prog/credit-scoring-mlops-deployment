"""Data drift detection via Evidently (feature distributions only; no target leak)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT
from src.monitoring.drift import (
    CATEGORICAL_PSI_COLUMNS,
    NUMERIC_PSI_COLUMNS,
    interpret_psi,
    population_stability_index,
    population_stability_index_categorical,
)
from src.monitoring.reports import monitoring_dir, utc_now_iso, write_report
from src.monitoring.thresholds import load_stage6_thresholds
from src.schema import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    detect_target,
)

EVIDENTLY_VERSION_PIN = "0.7.23"
_VALUE_DRIFT_RE = re.compile(r"ValueDrift\(column=([^,]+),")


def _exclude_target(columns: list[str], target: str | None) -> list[str]:
    blocked = {TARGET_COLUMN, "y", "target", "label"}
    if target:
        blocked.add(target)
    return [c for c in columns if c not in blocked]


def select_feature_columns(
    frame: pd.DataFrame,
    *,
    target: str | None = None,
    numerical: list[str] | None = None,
    categorical: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Pick numeric/categorical analysis columns without the target."""
    available = set(frame.columns)
    num = [
        c
        for c in (numerical or list(NUMERIC_FEATURES) + list(NUMERIC_PSI_COLUMNS))
        if c in available
    ]
    cat = [
        c
        for c in (
            categorical or list(CATEGORICAL_FEATURES) + list(CATEGORICAL_PSI_COLUMNS)
        )
        if c in available
    ]
    # Deduplicate while preserving order.
    num = list(dict.fromkeys(_exclude_target(num, target)))
    cat = list(dict.fromkeys(_exclude_target(cat, target)))
    # A column cannot be both; prefer categorical when listed as such.
    num = [c for c in num if c not in cat]
    return num, cat


def _psi_enrichment(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    numerical: list[str],
    categorical: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in numerical:
        if column not in reference.columns or column not in current.columns:
            continue
        try:
            value = population_stability_index(reference[column], current[column])
            rows.append(
                {
                    "feature": column,
                    "kind": "numeric",
                    "psi": value,
                    "interpretation": interpret_psi(value),
                }
            )
        except ValueError:
            continue
    for column in categorical:
        if column not in reference.columns or column not in current.columns:
            continue
        try:
            value = population_stability_index_categorical(
                reference[column], current[column]
            )
            rows.append(
                {
                    "feature": column,
                    "kind": "categorical",
                    "psi": value,
                    "interpretation": interpret_psi(value),
                }
            )
        except ValueError:
            continue
    return rows


def _parse_evidently_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    drift_share = 0.0
    drifted_count = 0
    per_feature: list[dict[str, Any]] = []
    for metric in metrics:
        name = str(metric.get("metric_name", ""))
        value = metric.get("value")
        config = metric.get("config") or {}
        if name.startswith("DriftedColumnsCount"):
            if isinstance(value, dict):
                drift_share = float(value.get("share", 0.0))
                drifted_count = int(value.get("count", 0))
            continue
        match = _VALUE_DRIFT_RE.search(name)
        if not match:
            continue
        column = match.group(1)
        threshold = float(config.get("threshold", 0.05))
        method = str(config.get("method", ""))
        # Evidently ValueDrift returns the statistic/p-value used by the method.
        # For "*p_value" methods, drift is typically declared when value < threshold.
        score = float(value) if value is not None else float("nan")
        drifted = False
        if "p_value" in method.lower():
            drifted = bool(score < threshold)
        else:
            drifted = bool(score > threshold)
        per_feature.append(
            {
                "feature": column,
                "method": method,
                "score": score,
                "threshold": threshold,
                "drifted": drifted,
            }
        )
    return {
        "drift_share": drift_share,
        "drifted_count": drifted_count,
        "features": per_feature,
    }


def run_data_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    target_column: str | None = None,
    thresholds: dict[str, Any] | None = None,
    save_html: bool = True,
    output_name: str = "data_drift",
) -> dict[str, Any]:
    """
    Compare feature distributions (reference vs current).

    Explicitly excludes the target from analysis features — this is *data* drift,
    not concept/label drift.
    """
    from evidently import Dataset, DataDefinition, Report
    from evidently.presets import DataDriftPreset
    import evidently

    cfg = (thresholds or load_stage6_thresholds()).get("data_drift", {})
    share_threshold = float(cfg.get("share_threshold", 0.3))
    min_rows = int(cfg.get("min_rows", 30))
    drift_share_preset = float(cfg.get("share_threshold", 0.3))

    target = target_column
    if target is None:
        try:
            target = detect_target(list(reference.columns) + list(current.columns))
        except ValueError:
            target = None

    numerical, categorical = select_feature_columns(reference, target=target)
    # Keep only columns present in both frames.
    numerical = [c for c in numerical if c in current.columns]
    categorical = [c for c in categorical if c in current.columns]
    feature_cols = numerical + categorical

    started = utc_now_iso()
    status = "ok"
    warnings: list[str] = []

    if len(reference) < min_rows or len(current) < min_rows:
        status = "insufficient_data"
        result = {
            "check_type": "data_drift",
            "status": status,
            "message": (
                f"Need at least {min_rows} rows in reference and current "
                f"(got {len(reference)} / {len(current)})."
            ),
            "reference_rows": int(len(reference)),
            "current_rows": int(len(current)),
            "min_rows": min_rows,
            "target_excluded": target,
            "features_analyzed": feature_cols,
            "data_drift_detected": False,
            "drift_share": None,
            "thresholds": {"share_threshold": share_threshold},
            "evidently_version": getattr(
                evidently, "__version__", EVIDENTLY_VERSION_PIN
            ),
            "started_at_utc": started,
            "finished_at_utc": utc_now_iso(),
            "note": (
                "Data drift checks feature distributions only. "
                "It is distinct from concept/quality degradation."
            ),
        }
        path = write_report(output_name, result, subdirectory="data_drift")
        result["report_path"] = str(path)
        return result

    if not feature_cols:
        raise ValueError("No feature columns left after excluding target")

    ref_view = reference[feature_cols].copy()
    cur_view = current[feature_cols].copy()

    definition = DataDefinition(
        numerical_columns=numerical or None,
        categorical_columns=categorical or None,
    )
    ref_ds = Dataset.from_pandas(ref_view, data_definition=definition)
    cur_ds = Dataset.from_pandas(cur_view, data_definition=definition)
    report = Report([DataDriftPreset(drift_share=drift_share_preset)])
    snapshot = report.run(cur_ds, ref_ds)
    parsed = _parse_evidently_metrics(list(snapshot.dict().get("metrics", [])))

    drift_share = float(parsed["drift_share"])
    detected = drift_share >= share_threshold
    psi_rows = _psi_enrichment(ref_view, cur_view, numerical, categorical)

    out_dir = monitoring_dir() / "data_drift"
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path: Path | None = None
    evidently_json_path = out_dir / f"{output_name}_evidently.json"
    snapshot.save_json(str(evidently_json_path))
    if save_html:
        html_path = out_dir / f"{output_name}.html"
        snapshot.save_html(str(html_path))

    if any(c not in feature_cols for c in (target,) if c):
        warnings.append("target excluded from feature set")

    result = {
        "check_type": "data_drift",
        "status": status,
        "reference_rows": int(len(reference)),
        "current_rows": int(len(current)),
        "min_rows": min_rows,
        "target_excluded": target,
        "numerical_features": numerical,
        "categorical_features": categorical,
        "features_analyzed": feature_cols,
        "drift_share": drift_share,
        "drifted_count": int(parsed["drifted_count"]),
        "data_drift_detected": bool(detected),
        "thresholds": {"share_threshold": share_threshold, "min_rows": min_rows},
        "per_feature": parsed["features"],
        "psi_enrichment": psi_rows,
        "evidently_version": getattr(evidently, "__version__", EVIDENTLY_VERSION_PIN),
        "evidently_json": str(evidently_json_path.relative_to(PROJECT_ROOT)),
        "evidently_html": (
            str(html_path.relative_to(PROJECT_ROOT)) if html_path else None
        ),
        "warnings": warnings,
        "started_at_utc": started,
        "finished_at_utc": utc_now_iso(),
        "note": (
            "Data drift = change in feature distributions. "
            "Does not by itself prove concept drift or model quality loss."
        ),
    }
    path = write_report(output_name, result, subdirectory="data_drift")
    result["report_path"] = str(path)
    return result
