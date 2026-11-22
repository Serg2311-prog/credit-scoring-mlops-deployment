"""Пути проекта и чтение params.yaml."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARAMS_PATH = PROJECT_ROOT / "params.yaml"


def load_params() -> dict[str, Any]:
    if not PARAMS_PATH.is_file():
        raise FileNotFoundError(f"Не найден файл параметров: {PARAMS_PATH}")
    with PARAMS_PATH.open(encoding="utf-8") as params_file:
        params = yaml.safe_load(params_file)
    if not isinstance(params, dict):
        raise ValueError("params.yaml должен содержать словарь параметров")
    return params


def raw_csv_candidates() -> list[Path]:
    filename = load_params()["prepare"]["raw_filename"]
    return [
        PROJECT_ROOT / "data" / "raw" / filename,
        PROJECT_ROOT / filename,
        PROJECT_ROOT.parent / filename,
    ]


def find_raw_csv() -> Path | None:
    for path in raw_csv_candidates():
        if path.is_file():
            return path
    return None


def require_raw_csv() -> Path:
    path = find_raw_csv()
    if path is None:
        searched = ", ".join(str(item) for item in raw_csv_candidates())
        raise FileNotFoundError("Не найден исходный CSV. Проверенные пути: " + searched)
    return path


def processed_dir() -> Path:
    return PROJECT_ROOT / "data" / "processed"


def models_dir() -> Path:
    return PROJECT_ROOT / "models"


def model_path() -> Path:
    """Путь baseline sklearn pickle (исторический RF из исходного проекта)."""
    return models_dir() / "credit_default_model.pkl"


def preprocessor_path() -> Path:
    return models_dir() / "preprocessor.joblib"


def nn_checkpoint_path() -> Path:
    return models_dir() / "credit_scoring_nn.pt"


def nn_onnx_path() -> Path:
    return models_dir() / "credit_scoring_nn.onnx"


def nn_quant_onnx_path() -> Path:
    return models_dir() / "credit_scoring_nn.quant.onnx"


def nn_metadata_path() -> Path:
    return models_dir() / "credit_scoring_nn_metadata.json"


def artifacts_dir() -> Path:
    return PROJECT_ROOT / "artifacts"


def baseline_metrics_path() -> Path:
    return artifacts_dir() / "baseline_metrics.json"


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Ожидался JSON-объект в {path}")
    return payload
