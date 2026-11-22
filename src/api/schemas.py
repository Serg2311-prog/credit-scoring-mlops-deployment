"""Pydantic-контракт API, согласованный с Pandera validation этапа 1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.data.validation import (
    EDUCATION_VALUES,
    MARRIAGE_VALUES,
    SEX_VALUES,
)


class ClientFeatures(BaseModel):
    """Сырые признаки клиента. ID и target не принимаются."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "LIMIT_BAL": 20000.0,
                "SEX": 2,
                "EDUCATION": 2,
                "MARRIAGE": 1,
                "AGE": 24,
                "PAY_0": 2,
                "PAY_2": 2,
                "PAY_3": -1,
                "PAY_4": -1,
                "PAY_5": -2,
                "PAY_6": -2,
                "BILL_AMT1": 3913.0,
                "BILL_AMT2": 3102.0,
                "BILL_AMT3": 689.0,
                "BILL_AMT4": 0.0,
                "BILL_AMT5": 0.0,
                "BILL_AMT6": 0.0,
                "PAY_AMT1": 0.0,
                "PAY_AMT2": 689.0,
                "PAY_AMT3": 0.0,
                "PAY_AMT4": 0.0,
                "PAY_AMT5": 0.0,
                "PAY_AMT6": 0.0,
            }
        },
    )

    LIMIT_BAL: float = Field(..., ge=0)
    SEX: int = Field(..., ge=1, le=2)
    EDUCATION: int = Field(..., ge=0, le=6)
    MARRIAGE: int = Field(..., ge=0, le=3)
    AGE: int = Field(..., ge=18, le=100)
    PAY_0: int = Field(..., ge=-2, le=8)
    PAY_2: int = Field(..., ge=-2, le=8)
    PAY_3: int = Field(..., ge=-2, le=8)
    PAY_4: int = Field(..., ge=-2, le=8)
    PAY_5: int = Field(..., ge=-2, le=8)
    PAY_6: int = Field(..., ge=-2, le=8)
    BILL_AMT1: float
    BILL_AMT2: float
    BILL_AMT3: float
    BILL_AMT4: float
    BILL_AMT5: float
    BILL_AMT6: float
    PAY_AMT1: float = Field(..., ge=0)
    PAY_AMT2: float = Field(..., ge=0)
    PAY_AMT3: float = Field(..., ge=0)
    PAY_AMT4: float = Field(..., ge=0)
    PAY_AMT5: float = Field(..., ge=0)
    PAY_AMT6: float = Field(..., ge=0)

    @field_validator(
        "LIMIT_BAL",
        "BILL_AMT1",
        "BILL_AMT2",
        "BILL_AMT3",
        "BILL_AMT4",
        "BILL_AMT5",
        "BILL_AMT6",
        "PAY_AMT1",
        "PAY_AMT2",
        "PAY_AMT3",
        "PAY_AMT4",
        "PAY_AMT5",
        "PAY_AMT6",
        mode="after",
    )
    @classmethod
    def _finite_float(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("value must be a finite number")
        return float(value)

    @field_validator("SEX")
    @classmethod
    def _sex_allowed(cls, value: int) -> int:
        if value not in SEX_VALUES:
            raise ValueError(f"SEX must be one of {SEX_VALUES}")
        return value

    @field_validator("EDUCATION")
    @classmethod
    def _education_allowed(cls, value: int) -> int:
        if value not in EDUCATION_VALUES:
            raise ValueError(f"EDUCATION must be one of {EDUCATION_VALUES}")
        return value

    @field_validator("MARRIAGE")
    @classmethod
    def _marriage_allowed(cls, value: int) -> int:
        if value not in MARRIAGE_VALUES:
            raise ValueError(f"MARRIAGE must be one of {MARRIAGE_VALUES}")
        return value


class BatchPredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ClientFeatures] = Field(..., min_length=1)


class PredictResponse(BaseModel):
    probability_default: float = Field(..., ge=0.0, le=1.0)
    prediction: Literal[0, 1]
    model_version: str
    request_id: str


class BatchPredictResponse(BaseModel):
    results: list[PredictResponse]
    model_version: str
    request_id: str
    batch_size: int


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    model_loaded: bool
    preprocessor_loaded: bool
    backend: str
    model_version: str


class ModelInfoResponse(BaseModel):
    model_name: str
    model_version: str
    backend: str
    model_format: str
    input_features_count: int
    threshold: float
    max_batch_size: int


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    request_id: str
    details: object | None = None
