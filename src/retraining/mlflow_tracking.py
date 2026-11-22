"""Optional MLflow tracking with file-based fallback (no cloud required)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import dump_json
from src.retraining.config import load_retraining_config


def log_run(
    *,
    run_directory: Path,
    params: dict[str, Any],
    metrics: dict[str, Any],
    tags: dict[str, Any] | None = None,
    artifact_paths: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_retraining_config()
    ml_cfg = cfg.get("mlflow", {})
    enabled = bool(ml_cfg.get("enabled", False))
    payload = {
        "tracking": "mlflow" if enabled else "file_fallback",
        "experiment_name": ml_cfg.get("experiment_name", "credit-scoring-retraining"),
        "params": params,
        "metrics": metrics,
        "tags": tags or {},
        "artifacts": artifact_paths or [],
        "run_directory": str(run_directory),
    }

    if enabled:
        try:
            import mlflow

            tracking_uri = ml_cfg.get("tracking_uri", "file:./mlruns")
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment(str(payload["experiment_name"]))
            with mlflow.start_run() as active:
                mlflow.log_params(
                    {k: str(v)[:250] for k, v in params.items() if v is not None}
                )
                flat_metrics = {}
                for key, value in metrics.items():
                    if isinstance(value, (int, float)) and value is not None:
                        flat_metrics[key] = float(value)
                mlflow.log_metrics(flat_metrics)
                for tag_k, tag_v in (tags or {}).items():
                    mlflow.set_tag(str(tag_k), str(tag_v))
                for art in artifact_paths or []:
                    path = Path(art)
                    if path.is_file():
                        mlflow.log_artifact(str(path))
                payload["run_id"] = active.info.run_id
                payload["tracking_uri"] = tracking_uri
        except Exception as exc:  # noqa: BLE001
            payload["tracking"] = "file_fallback"
            payload["mlflow_error"] = str(exc)

    if "run_id" not in payload:
        payload["run_id"] = run_directory.name

    dump_json(run_directory / "mlflow_style_meta.json", payload)
    return payload
