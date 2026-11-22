"""Общие утилиты runtime: seeds, device, загрузка checkpoint, инференс."""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch

from src.config import load_params, nn_checkpoint_path
from src.nn.model import CreditScoringMLP, build_mlp_from_params


def configure_cpu_threads(num_threads: int | None = None) -> int:
    params = load_params().get("nn", {})
    threads = int(
        num_threads if num_threads is not None else params.get("num_threads", 2)
    )
    threads = max(1, threads)
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(threads))
    torch.set_num_threads(threads)
    if hasattr(torch, "set_num_interop_threads"):
        try:
            torch.set_num_interop_threads(max(1, min(threads, 2)))
        except RuntimeError:
            # Уже инициализировано в процессе — оставляем как есть.
            pass
    return threads


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def resolve_device(requested: str = "cpu") -> torch.device:
    requested = (requested or "cpu").lower()
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA недоступна на этой машине")
        return torch.device("cuda")
    return torch.device("cpu")


def load_checkpoint(
    path: Path | None = None,
    map_location: str | torch.device = "cpu",
) -> tuple[CreditScoringMLP, dict[str, Any]]:
    checkpoint_file = path or nn_checkpoint_path()
    if not checkpoint_file.is_file():
        raise FileNotFoundError(f"Checkpoint не найден: {checkpoint_file}")
    payload = torch.load(checkpoint_file, map_location=map_location, weights_only=False)
    if not isinstance(payload, dict) or "state_dict" not in payload:
        raise ValueError(f"Некорректный checkpoint: {checkpoint_file}")
    config = payload.get("model_config") or {}
    model = build_mlp_from_params(
        input_dim=int(config["input_dim"]),
        nn_params={
            "hidden_dims": config.get("hidden_dims", [128, 64]),
            "dropout": config.get("dropout", 0.2),
        },
    )
    model.load_state_dict(payload["state_dict"])
    model.to(map_location)
    model.eval()
    return model, payload


def probabilities_from_logits(logits: np.ndarray | torch.Tensor) -> np.ndarray:
    if isinstance(logits, torch.Tensor):
        logits_np = logits.detach().cpu().numpy()
    else:
        logits_np = np.asarray(logits, dtype=np.float64)
    # numerically stable sigmoid
    return 1.0 / (1.0 + np.exp(-logits_np))
