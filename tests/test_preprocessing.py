"""Тесты sklearn preprocessing для NN-пайплайна."""

import numpy as np
import pytest

from src.models.preprocessing import (
    create_feature_preprocessor,
    fit_preprocessor,
    preprocessor_input_dim,
    transform_features,
)
from src.schema import RAW_FEATURE_COLUMNS


def test_preprocessor_fits_on_train_only(raw_frame):
    train = raw_frame.iloc[:60].copy()
    test = raw_frame.iloc[60:].copy()
    test["LIMIT_BAL"] = 1_000_000
    preprocessor = fit_preprocessor(train[RAW_FEATURE_COLUMNS])
    scaler = (
        preprocessor.named_steps["preprocess"]
        .named_transformers_["num"]
        .named_steps["scaler"]
    )
    from src.features.build_features import add_features
    from src.schema import NUMERIC_FEATURES

    transformed_train = add_features(train)
    limit_index = NUMERIC_FEATURES.index("LIMIT_BAL")
    assert np.isclose(scaler.mean_[limit_index], transformed_train["LIMIT_BAL"].mean())
    assert not np.isclose(scaler.mean_[limit_index], test["LIMIT_BAL"].mean())


def test_transform_returns_float32_matrix(raw_frame):
    preprocessor = fit_preprocessor(raw_frame[RAW_FEATURE_COLUMNS])
    matrix = transform_features(preprocessor, raw_frame[RAW_FEATURE_COLUMNS])
    assert isinstance(matrix, np.ndarray)
    assert matrix.dtype == np.float32
    assert matrix.shape[0] == len(raw_frame)
    assert matrix.shape[1] == preprocessor_input_dim(preprocessor)
    assert np.isfinite(matrix).all()


def test_transform_drops_target_and_rejects_non_dataframe(raw_frame):
    preprocessor = fit_preprocessor(raw_frame[RAW_FEATURE_COLUMNS])
    with_target = transform_features(preprocessor, raw_frame)
    without = transform_features(preprocessor, raw_frame[RAW_FEATURE_COLUMNS])
    assert with_target.shape == without.shape
    with pytest.raises(TypeError):
        fit_preprocessor(raw_frame[RAW_FEATURE_COLUMNS].to_numpy())


def test_create_feature_preprocessor_has_expected_steps():
    pipe = create_feature_preprocessor()
    assert list(pipe.named_steps) == ["features", "preprocess"]


def test_feature_contract_preserves_column_order(raw_frame):
    from src.models.preprocessing import preprocessor_metadata
    from src.schema import MODEL_FEATURE_COLUMNS, RAW_FEATURE_COLUMNS

    preprocessor = fit_preprocessor(raw_frame[RAW_FEATURE_COLUMNS])
    contract = preprocessor_metadata(preprocessor)
    assert contract["raw_feature_columns"] == list(RAW_FEATURE_COLUMNS)
    assert contract["model_feature_columns"] == list(MODEL_FEATURE_COLUMNS)
    assert contract["input_dim"] == len(contract["transformed_feature_names"])
    # Перестановка raw-колонок не должна менять выход при явном reorder в transform
    shuffled = raw_frame[list(reversed(RAW_FEATURE_COLUMNS))]
    # transform_features uses model_input_frame then FeatureEngineer which selects
    # RAW_FEATURE_COLUMNS in canonical order via add_features.
    matrix_a = transform_features(preprocessor, raw_frame[RAW_FEATURE_COLUMNS])
    matrix_b = transform_features(preprocessor, shuffled)
    assert np.allclose(matrix_a, matrix_b)
