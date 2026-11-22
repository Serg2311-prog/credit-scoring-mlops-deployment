"""Sklearn preprocessing без классификатора: raw features -> dense float matrix.

Препроцессор (FeatureEngineer + ColumnTransformer) обучается только на train.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from src.config import preprocessor_path
from src.models.pipeline import create_pipeline
from src.models.predict import model_input_frame
from src.schema import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    RAW_FEATURE_COLUMNS,
)


class _IdentityEstimator:
    """Заглушка для reuse create_pipeline без реального классификатора."""

    def fit(self, X, y=None):  # noqa: N803
        return self

    def predict(self, X):  # noqa: N803
        return np.zeros(len(X), dtype=int)


def create_feature_preprocessor() -> Pipeline:
    """Pipeline: FeatureEngineer -> impute/scale/OHE. Без модели."""
    full = create_pipeline(_IdentityEstimator())
    return Pipeline(
        steps=[
            ("features", full.named_steps["features"]),
            ("preprocess", full.named_steps["preprocess"]),
        ]
    )


def fit_preprocessor(raw_features: pd.DataFrame) -> Pipeline:
    if not isinstance(raw_features, pd.DataFrame):
        raise TypeError("fit_preprocessor ожидает pandas.DataFrame")
    preprocessor = create_feature_preprocessor()
    preprocessor.fit(raw_features)
    return preprocessor


def transform_features(
    preprocessor: Pipeline, raw_features: pd.DataFrame
) -> np.ndarray:
    features = model_input_frame(raw_features)
    matrix = preprocessor.transform(features)
    return np.asarray(matrix, dtype=np.float32)


def save_preprocessor(preprocessor: Pipeline, path: Path | None = None) -> Path:
    destination = path or preprocessor_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(preprocessor, destination)
    return destination


def load_preprocessor(path: Path | None = None) -> Pipeline:
    source = path or preprocessor_path()
    if not source.is_file():
        raise FileNotFoundError(f"Препроцессор не найден: {source}")
    return joblib.load(source)


def preprocessor_input_dim(preprocessor: Pipeline) -> int:
    probe = preprocessor.named_steps["preprocess"]
    if hasattr(probe, "n_features_out_") and probe.n_features_out_ is not None:
        return int(probe.n_features_out_)
    # Fallback for older sklearn: transform one empty-like frame is avoided;
    # use get_feature_names_out when available.
    if hasattr(probe, "get_feature_names_out"):
        return int(len(probe.get_feature_names_out()))
    raise RuntimeError("Не удалось определить размерность после preprocessing")


def transformed_feature_names(preprocessor: Pipeline) -> list[str]:
    probe = preprocessor.named_steps["preprocess"]
    if hasattr(probe, "get_feature_names_out"):
        return [str(name) for name in probe.get_feature_names_out()]
    return [f"f{index}" for index in range(preprocessor_input_dim(preprocessor))]


def preprocessor_metadata(preprocessor: Pipeline) -> dict[str, Any]:
    """Контракт признаков обучения/serving: фиксированный порядок колонок."""
    return {
        "input_dim": preprocessor_input_dim(preprocessor),
        "steps": [name for name, _ in preprocessor.steps],
        "raw_feature_columns": list(RAW_FEATURE_COLUMNS),
        "model_feature_columns": list(MODEL_FEATURE_COLUMNS),
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "transformed_feature_names": transformed_feature_names(preprocessor),
        "notes": (
            "FeatureEngineer возвращает MODEL_FEATURE_COLUMNS в фиксированном порядке; "
            "ColumnTransformer применяет NUMERIC_FEATURES затем CATEGORICAL_FEATURES; "
            "ONNX получает densematrix той же размерности/порядка."
        ),
    }
