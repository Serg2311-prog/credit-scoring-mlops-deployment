"""Компактная MLP для бинарного кредитного скоринга."""

from __future__ import annotations

from typing import Any, Sequence

import torch
from torch import nn


class CreditScoringMLP(nn.Module):
    """MLP: Linear -> BatchNorm -> ReLU -> Dropout (×N) -> Linear logits."""

    def __init__(
        self,
        input_dim: int,
        hidden_dims: Sequence[int] | None = None,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        if input_dim <= 0:
            raise ValueError("input_dim должен быть положительным")
        dims = list(hidden_dims) if hidden_dims is not None else [128, 64]
        if not dims:
            raise ValueError("hidden_dims не должен быть пустым")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("dropout должен быть в [0, 1)")

        layers: list[nn.Module] = []
        previous = int(input_dim)
        for width in dims:
            width = int(width)
            if width <= 0:
                raise ValueError("Размер скрытого слоя должен быть положительным")
            layers.append(nn.Linear(previous, width))
            layers.append(nn.BatchNorm1d(width))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            previous = width
        layers.append(nn.Linear(previous, 1))
        self.network = nn.Sequential(*layers)
        self.input_dim = int(input_dim)
        self.hidden_dims = [int(item) for item in dims]
        self.dropout = float(dropout)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        # Проверки только вне tracing/export, иначе ONNX получает ложные константы.
        if not torch.jit.is_tracing():
            if features.ndim != 2:
                raise ValueError("Ожидается тензор формы [batch, features]")
            if int(features.shape[1]) != self.input_dim:
                raise ValueError(
                    f"Ожидалась размерность {self.input_dim}, "
                    f"получено {features.shape[1]}"
                )
        logits = self.network(features)
        return logits.squeeze(-1)

    def predict_proba(self, features: torch.Tensor) -> torch.Tensor:
        self.eval()
        with torch.no_grad():
            logits = self.forward(features)
            return torch.sigmoid(logits)


def build_mlp_from_params(
    input_dim: int, nn_params: dict[str, Any]
) -> CreditScoringMLP:
    return CreditScoringMLP(
        input_dim=input_dim,
        hidden_dims=nn_params.get("hidden_dims", [128, 64]),
        dropout=float(nn_params.get("dropout", 0.2)),
    )


def model_config_dict(model: CreditScoringMLP) -> dict[str, Any]:
    return {
        "input_dim": model.input_dim,
        "hidden_dims": list(model.hidden_dims),
        "dropout": model.dropout,
        "architecture": "CreditScoringMLP",
    }
