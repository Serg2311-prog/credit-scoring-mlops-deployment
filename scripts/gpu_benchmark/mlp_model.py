"""Minimal CreditScoringMLP matching production checkpoint (input_dim=47)."""

from __future__ import annotations

from typing import Any, Sequence

import torch
from torch import nn


class CreditScoringMLP(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dims: Sequence[int] | None = None,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        dims = list(hidden_dims) if hidden_dims is not None else [128, 64]
        layers: list[nn.Module] = []
        previous = int(input_dim)
        for width in dims:
            width = int(width)
            layers.append(nn.Linear(previous, width))
            layers.append(nn.BatchNorm1d(width))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            previous = width
        layers.append(nn.Linear(previous, 1))
        self.network = nn.Sequential(*layers)
        self.input_dim = int(input_dim)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        logits = self.network(features)
        return logits.squeeze(-1)


def load_mlp_checkpoint(path: str, map_location: str = "cpu") -> CreditScoringMLP:
    """Load checkpoint; prefer weights_only=True when payload is compatible."""
    try:
        payload: Any = torch.load(path, map_location=map_location, weights_only=True)
    except Exception:  # noqa: BLE001
        payload = torch.load(path, map_location=map_location, weights_only=False)
    if not isinstance(payload, dict) or "state_dict" not in payload:
        raise ValueError(f"Unexpected checkpoint format: {path}")
    cfg = payload.get("model_config") or {}
    if "input_dim" not in cfg and "input_dim" in payload:
        cfg = {
            "input_dim": payload["input_dim"],
            "hidden_dims": (payload.get("nn_params") or {}).get(
                "hidden_dims", [128, 64]
            ),
            "dropout": (payload.get("nn_params") or {}).get("dropout", 0.2),
        }
    model = CreditScoringMLP(
        input_dim=int(cfg["input_dim"]),
        hidden_dims=cfg.get("hidden_dims", [128, 64]),
        dropout=float(cfg.get("dropout", 0.2)),
    )
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model
