"""Train a candidate model into a run directory (never overwrites production)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from src.config import dump_json
from src.models.evaluate import compute_metrics
from src.models.preprocessing import (
    fit_preprocessor,
    preprocessor_input_dim,
    save_preprocessor,
    transform_features,
)
from src.retraining.config import load_retraining_config
from src.retraining.exceptions import RetrainingError
from src.schema import RAW_FEATURE_COLUMNS


def _features_and_target(
    frame: pd.DataFrame, target: str
) -> tuple[pd.DataFrame, np.ndarray]:
    cols = [c for c in RAW_FEATURE_COLUMNS if c in frame.columns and c != target]
    x = frame.loc[:, cols]
    y = frame[target].astype(int).to_numpy()
    return x, y


def train_candidate_logistic(
    train_df: pd.DataFrame,
    target: str,
    *,
    run_directory: Path,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_retraining_config()
    rt = cfg.get("retraining", {})
    seed = int(rt.get("random_state", 42))
    threshold = float(rt.get("decision_threshold", 0.5))
    log_cfg = rt.get("logistic", {})
    val_size = float(rt.get("test_size", 0.2))

    x_raw, y = _features_and_target(train_df, target)
    x_fit_raw, x_val_raw, y_fit, y_val = train_test_split(
        x_raw, y, test_size=val_size, random_state=seed, stratify=y
    )

    preprocessor = fit_preprocessor(x_fit_raw)
    x_fit = transform_features(preprocessor, x_fit_raw)
    x_val = transform_features(preprocessor, x_val_raw)

    model = LogisticRegression(
        max_iter=int(log_cfg.get("max_iter", 500)),
        C=float(log_cfg.get("C", 1.0)),
        random_state=seed,
        solver="lbfgs",
    )
    model.fit(x_fit, y_fit)

    # Refit preprocessor + model on full train (val only for early visibility).
    final_pre = fit_preprocessor(x_raw)
    x_all = transform_features(final_pre, x_raw)
    final_model = LogisticRegression(
        max_iter=int(log_cfg.get("max_iter", 500)),
        C=float(log_cfg.get("C", 1.0)),
        random_state=seed,
        solver="lbfgs",
    )
    final_model.fit(x_all, y)

    val_proba = model.predict_proba(x_val)[:, 1]
    val_metrics = compute_metrics(y_val, val_proba, threshold=threshold)
    train_proba = final_model.predict_proba(x_all)[:, 1]
    train_metrics = compute_metrics(y, train_proba, threshold=threshold)

    run_directory.mkdir(parents=True, exist_ok=True)
    pre_path = run_directory / "candidate_preprocessor.joblib"
    model_path = run_directory / "candidate_model.joblib"
    save_preprocessor(final_pre, pre_path)
    joblib.dump(final_model, model_path)

    meta = {
        "backend": "logistic",
        "random_state": seed,
        "input_dim": int(preprocessor_input_dim(final_pre)),
        "decision_threshold": threshold,
        "preprocessor_path": str(pre_path),
        "model_path": str(model_path),
        "train_rows": int(len(train_df)),
        "fit_rows": int(len(x_fit_raw)),
        "val_rows": int(len(x_val_raw)),
        "metrics": {
            "train": train_metrics,
            "val_selection_only": val_metrics,
            "note": (
                "Val metrics are diagnostic only. Gate decisions use holdout "
                "in evaluation.py — never train metrics."
            ),
        },
        "overwrites_production": False,
    }
    dump_json(run_directory / "candidate_train_meta.json", meta)
    return meta


def _score_mlp(matrix: np.ndarray, model_path: Path) -> np.ndarray:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover
        raise RetrainingError(
            "backend=mlp scoring requires torch; install requirements-nn.txt"
        ) from exc

    from src.nn.model import build_mlp_from_params
    from src.nn.runtime import probabilities_from_logits

    payload = torch.load(model_path, map_location="cpu", weights_only=False)
    model_config = dict(payload.get("model_config") or {})
    input_dim = int(model_config.get("input_dim") or matrix.shape[1])
    if matrix.shape[1] != input_dim:
        raise RetrainingError(
            f"MLP input dim mismatch: matrix={matrix.shape[1]} meta={input_dim}"
        )
    nn_params = {
        "hidden_dims": model_config.get("hidden_dims", [64, 32]),
        "dropout": float(model_config.get("dropout", 0.0)),
    }
    model = build_mlp_from_params(input_dim, nn_params)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    with torch.no_grad():
        logits = model(torch.from_numpy(matrix.astype(np.float32)))
        return np.asarray(probabilities_from_logits(logits), dtype=float)


def score_candidate(
    *,
    preprocessor_path: Path,
    model_path: Path,
    frame: pd.DataFrame,
    target: str,
    backend: str = "logistic",
) -> np.ndarray:
    if target in frame.columns:
        x = frame.drop(columns=[target])
    else:
        x = frame
    cols = [c for c in RAW_FEATURE_COLUMNS if c in x.columns]
    x = x.loc[:, cols]
    preprocessor = joblib.load(preprocessor_path)
    matrix = transform_features(preprocessor, x)
    backend = str(backend).lower()
    if backend == "logistic":
        model = joblib.load(model_path)
        return np.asarray(model.predict_proba(matrix)[:, 1], dtype=float)
    if backend == "mlp":
        return _score_mlp(matrix, Path(model_path))
    raise RetrainingError(
        f"Unsupported scoring backend: {backend}. Supported: logistic, mlp"
    )


def train_candidate(
    train_df: pd.DataFrame,
    target: str,
    *,
    run_directory: Path,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_retraining_config()
    backend = str(cfg.get("retraining", {}).get("backend", "logistic")).lower()
    if backend == "logistic":
        return train_candidate_logistic(
            train_df, target, run_directory=run_directory, cfg=cfg
        )
    if backend == "mlp":
        return _train_candidate_mlp(
            train_df, target, run_directory=run_directory, cfg=cfg
        )
    raise RetrainingError(
        f"Unknown retraining backend: {backend}. Supported: logistic, mlp"
    )


def _train_candidate_mlp(
    train_df: pd.DataFrame,
    target: str,
    *,
    run_directory: Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Short MLP candidate train; preprocessor and weights stay dimension-aligned."""
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:  # pragma: no cover
        raise RetrainingError(
            "backend=mlp requires torch; install requirements-nn.txt "
            "or set retraining.backend: logistic"
        ) from exc

    from src.nn.model import build_mlp_from_params
    from src.nn.runtime import (
        configure_cpu_threads,
        probabilities_from_logits,
        set_seed,
    )

    rt = cfg.get("retraining", {})
    mlp_cfg = dict(rt.get("mlp", {}))
    seed = int(rt.get("random_state", 42))
    threshold = float(rt.get("decision_threshold", 0.5))
    configure_cpu_threads(int(mlp_cfg.get("num_threads", 1)))
    set_seed(seed)

    x_raw, y = _features_and_target(train_df, target)
    # Fit preprocessor once on full train so scoring uses the same transform.
    final_pre = fit_preprocessor(x_raw)
    x_all = transform_features(final_pre, x_raw)
    input_dim = preprocessor_input_dim(final_pre)
    x_fit, x_val, y_fit, y_val = train_test_split(
        x_all,
        y,
        test_size=float(rt.get("test_size", 0.2)),
        random_state=seed,
        stratify=y,
    )

    nn_params = {
        "hidden_dims": mlp_cfg.get("hidden_dims", [64, 32]),
        "dropout": float(mlp_cfg.get("dropout", 0.2)),
    }
    device = torch.device("cpu")
    model = build_mlp_from_params(input_dim, nn_params).to(device)
    pos_weight = torch.tensor(
        [float((y_fit == 0).sum()) / max(float((y_fit == 1).sum()), 1.0)]
    )
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(mlp_cfg.get("learning_rate", 0.001)),
        weight_decay=float(mlp_cfg.get("weight_decay", 0.0001)),
    )
    loader = DataLoader(
        TensorDataset(
            torch.from_numpy(x_fit.astype(np.float32)),
            torch.from_numpy(y_fit.astype(np.float32)),
        ),
        batch_size=int(mlp_cfg.get("batch_size", 64)),
        shuffle=True,
    )
    epochs = int(mlp_cfg.get("epochs", 8))
    patience = int(mlp_cfg.get("early_stopping_patience", 3))
    best_auc = -1.0
    best_state = None
    wait = 0
    for _ in range(epochs):
        model.train()
        for bx, by in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(bx), by)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_logits = model(torch.from_numpy(x_val.astype(np.float32)))
            val_prob = probabilities_from_logits(val_logits)
        val_metrics = compute_metrics(y_val, val_prob, threshold=threshold)
        if val_metrics["roc_auc"] > best_auc + 1e-6:
            best_auc = float(val_metrics["roc_auc"])
            best_state = {
                k: v.detach().cpu().clone() for k, v in model.state_dict().items()
            }
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break
    if best_state is None:
        raise RetrainingError("MLP candidate training produced no improvement on val")

    run_directory.mkdir(parents=True, exist_ok=True)
    pre_path = run_directory / "candidate_preprocessor.joblib"
    ckpt_path = run_directory / "candidate_model.pt"
    save_preprocessor(final_pre, pre_path)
    torch.save(
        {
            "state_dict": best_state,
            "model_config": {"input_dim": int(input_dim), **nn_params},
            "backend": "mlp",
        },
        ckpt_path,
    )
    meta = {
        "backend": "mlp",
        "random_state": seed,
        "input_dim": int(input_dim),
        "decision_threshold": threshold,
        "preprocessor_path": str(pre_path),
        "model_path": str(ckpt_path),
        "best_val_roc_auc": best_auc,
        "overwrites_production": False,
        "metrics": {
            "val_selection_only": {"roc_auc": best_auc},
            "note": "Holdout evaluation uses the same preprocessor + MLP weights.",
        },
    }
    dump_json(run_directory / "candidate_train_meta.json", meta)
    return meta
