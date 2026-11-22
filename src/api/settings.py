"""Конфигурация inference API из переменных окружения."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config import PROJECT_ROOT, nn_onnx_path, preprocessor_path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = Field(default="local", alias="APP_ENV")
    model_backend: str = Field(default="onnx", alias="MODEL_BACKEND")
    model_name: str = Field(default="credit_scoring_mlp", alias="MODEL_NAME")
    model_version: str = Field(default="mlp-onnx-fp32-v1", alias="MODEL_VERSION")
    model_path: Path = Field(default_factory=nn_onnx_path, alias="MODEL_PATH")
    preprocessor_path: Path = Field(
        default_factory=preprocessor_path, alias="PREPROCESSOR_PATH"
    )
    # Совпадает с params.yaml nn.threshold этапа 1.
    prediction_threshold: float = Field(default=0.5, alias="PREDICTION_THRESHOLD")
    max_batch_size: int = Field(default=256, alias="MAX_BATCH_SIZE", ge=1)
    ort_intra_op_threads: int = Field(default=2, alias="ORT_INTRA_OP_THREADS", ge=1)
    ort_inter_op_threads: int = Field(default=1, alias="ORT_INTER_OP_THREADS", ge=1)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    expected_input_dim: int = Field(default=47, alias="EXPECTED_INPUT_DIM", ge=1)

    # Stage 6 A/B (disabled by default — no automatic production switch).
    ab_enabled: bool = Field(default=False, alias="AB_ENABLED")
    ab_challenger_share: float = Field(
        default=0.2, alias="AB_CHALLENGER_SHARE", ge=0.0, le=1.0
    )
    ab_hash_salt: str = Field(default="credit-scoring-ab-v1", alias="AB_HASH_SALT")
    challenger_model_version: str = Field(
        default="challenger-candidate-v1", alias="CHALLENGER_MODEL_VERSION"
    )
    challenger_model_path: Path | None = Field(
        default=None, alias="CHALLENGER_MODEL_PATH"
    )

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
