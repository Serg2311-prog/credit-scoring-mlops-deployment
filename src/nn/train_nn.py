"""Обучение MLP. Hyperparameters / early stopping — только на train/val, не на test."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from src.config import (
    artifacts_dir,
    baseline_metrics_path,
    dump_json,
    load_json,
    load_params,
    nn_checkpoint_path,
    nn_metadata_path,
    processed_dir,
)
from src.models.evaluate import compute_metrics
from src.models.preprocessing import (
    fit_preprocessor,
    preprocessor_input_dim,
    preprocessor_metadata,
    save_preprocessor,
    transform_features,
)
from src.nn.model import build_mlp_from_params, model_config_dict
from src.nn.runtime import configure_cpu_threads, probabilities_from_logits, set_seed
from src.schema import detect_target


def _load_processed() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    params = load_params()
    train_path = processed_dir() / "train.csv"
    test_path = processed_dir() / "test.csv"
    if not train_path.is_file() or not test_path.is_file():
        raise FileNotFoundError(
            "Нет data/processed/train.csv или test.csv. "
            "Сначала выполните: python -m src.data.make_dataset"
        )
    train_df = pd.read_csv(train_path)
    test_df = pd.read_csv(test_path)
    target = detect_target(
        train_df.columns, preferred=params["prepare"]["target_column"]
    )
    return train_df, test_df, target


def _make_loader(
    features: np.ndarray,
    labels: np.ndarray,
    batch_size: int,
    shuffle: bool,
) -> DataLoader:
    dataset = TensorDataset(
        torch.from_numpy(features.astype(np.float32)),
        torch.from_numpy(labels.astype(np.float32)),
    )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        drop_last=False,
        num_workers=0,
    )


def _predict_probabilities(
    model: nn.Module, features: np.ndarray, device: torch.device
) -> np.ndarray:
    model.eval()
    chunks: list[np.ndarray] = []
    batch_size = 1024
    with torch.no_grad():
        for start in range(0, len(features), batch_size):
            batch = torch.from_numpy(features[start : start + batch_size]).to(device)
            logits = model(batch)
            chunks.append(probabilities_from_logits(logits))
    if not chunks:
        return np.array([], dtype=np.float64)
    return np.concatenate(chunks, axis=0)


def train_mlp(device_name: str = "cpu") -> dict[str, Any]:
    params = load_params()
    nn_params = params["nn"]
    prepare = params["prepare"]
    seed = int(nn_params["random_state"])
    threads = configure_cpu_threads(int(nn_params.get("num_threads", 2)))
    set_seed(seed)

    if device_name == "cuda" and not torch.cuda.is_available():
        print("CUDA недоступна — обучение переключено на CPU")
        device_name = "cpu"
    device = torch.device(device_name)

    train_df, test_df, target = _load_processed()
    expected_train = 24000
    expected_test = 6000
    if len(train_df) != expected_train or len(test_df) != expected_test:
        print(
            "Предупреждение: ожидались "
            f"{expected_train}/{expected_test} строк train/test, "
            f"получено {len(train_df)}/{len(test_df)}"
        )

    x_train_raw = train_df.drop(columns=[target])
    y_train_full = train_df[target].astype(int).to_numpy()
    x_test_raw = test_df.drop(columns=[target])
    y_test = test_df[target].astype(int).to_numpy()

    # Внутренний val только из train. Test не участвует в выборе модели.
    x_fit_raw, x_val_raw, y_fit, y_val = train_test_split(
        x_train_raw,
        y_train_full,
        test_size=float(nn_params["val_size"]),
        random_state=seed,
        stratify=y_train_full,
    )

    preprocessor = fit_preprocessor(x_fit_raw)
    x_fit = transform_features(preprocessor, x_fit_raw)
    x_val = transform_features(preprocessor, x_val_raw)
    # Для финального артефакта препроцессор переобучаем на всём train
    # после выбора эпохи по val (см. ниже retrain). Пока логируем dim.
    input_dim = preprocessor_input_dim(preprocessor)

    positive = float(y_fit.sum())
    negative = float(len(y_fit) - positive)
    pos_weight = torch.tensor([negative / max(positive, 1.0)], dtype=torch.float32)

    model = build_mlp_from_params(input_dim, nn_params).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight.to(device))
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(nn_params["learning_rate"]),
        weight_decay=float(nn_params["weight_decay"]),
    )

    batch_size = int(nn_params["batch_size"])
    train_loader = _make_loader(x_fit, y_fit, batch_size=batch_size, shuffle=True)
    epochs = int(nn_params["epochs"])
    patience = int(nn_params["early_stopping_patience"])
    threshold = float(nn_params.get("threshold", 0.5))

    history: list[dict[str, Any]] = []
    best_val_auc = -1.0
    best_epoch = 0
    wait = 0
    saw_improvement = False

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        seen = 0
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item()) * len(batch_x)
            seen += len(batch_x)

        train_prob = _predict_probabilities(model, x_fit, device)
        val_prob = _predict_probabilities(model, x_val, device)
        train_metrics = compute_metrics(y_fit, train_prob, threshold=threshold)
        val_metrics = compute_metrics(y_val, val_prob, threshold=threshold)
        epoch_loss = running_loss / max(seen, 1)
        record = {
            "epoch": epoch,
            "loss": epoch_loss,
            "train_roc_auc": train_metrics["roc_auc"],
            "val_roc_auc": val_metrics["roc_auc"],
            "val_f1": val_metrics["f1"],
        }
        history.append(record)
        print(
            f"epoch {epoch:02d}: loss={epoch_loss:.4f} "
            f"train_auc={train_metrics['roc_auc']:.4f} "
            f"val_auc={val_metrics['roc_auc']:.4f}"
        )

        if val_metrics["roc_auc"] > best_val_auc + 1e-6:
            best_val_auc = float(val_metrics["roc_auc"])
            best_epoch = epoch
            saw_improvement = True
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                print(f"Early stopping на эпохе {epoch} (best={best_epoch})")
                break

    if not saw_improvement:
        raise RuntimeError("Обучение не зафиксировало улучшение val ROC-AUC")

    # Production artifacts: preprocessor fit на всём train (без test) +
    # повторное обучение MLP ровно best_epoch эпох на полном train.
    # Test используется только для финальной оценки ниже.
    final_preprocessor = fit_preprocessor(x_train_raw)
    x_train_all = transform_features(final_preprocessor, x_train_raw)
    x_test_final = transform_features(final_preprocessor, x_test_raw)
    final_dim = preprocessor_input_dim(final_preprocessor)
    if final_dim != input_dim:
        print(
            f"Размерность после полного train preprocessor: {final_dim} "
            f"(val-stage было {input_dim}). Переобучаем MLP на полном train."
        )

    set_seed(seed)
    final_model = build_mlp_from_params(final_dim, nn_params).to(device)
    pos_weight_full = torch.tensor(
        [float((y_train_full == 0).sum()) / max(float((y_train_full == 1).sum()), 1.0)],
        dtype=torch.float32,
    )
    final_criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight_full.to(device))
    final_optimizer = torch.optim.Adam(
        final_model.parameters(),
        lr=float(nn_params["learning_rate"]),
        weight_decay=float(nn_params["weight_decay"]),
    )
    full_loader = _make_loader(
        x_train_all, y_train_full, batch_size=batch_size, shuffle=True
    )
    retrain_epochs = max(1, best_epoch)
    for epoch in range(1, retrain_epochs + 1):
        final_model.train()
        for batch_x, batch_y in full_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            final_optimizer.zero_grad(set_to_none=True)
            logits = final_model(batch_x)
            loss = final_criterion(logits, batch_y)
            loss.backward()
            final_optimizer.step()

    train_prob = _predict_probabilities(final_model, x_train_all, device)
    test_prob = _predict_probabilities(final_model, x_test_final, device)
    train_metrics = compute_metrics(y_train_full, train_prob, threshold=threshold)
    test_metrics = compute_metrics(y_test, test_prob, threshold=threshold)

    preprocessor_file = save_preprocessor(final_preprocessor)
    feature_contract = preprocessor_metadata(final_preprocessor)
    dump_json(artifacts_dir() / "feature_contract.json", feature_contract)
    checkpoint_file = nn_checkpoint_path()
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    model_config = model_config_dict(final_model)
    checkpoint_payload = {
        "state_dict": final_model.state_dict(),
        "model_config": model_config,
        "feature_contract": feature_contract,
        "nn_params": nn_params,
        "prepare": prepare,
        "best_val_roc_auc": best_val_auc,
        "best_epoch": best_epoch,
        "retrain_epochs": retrain_epochs,
        "input_dim": final_dim,
        "threads": threads,
        "device": str(device),
        "pos_weight": float(pos_weight_full.item()),
        "note": (
            "Hyperparameters/early stopping выбирались по stratified val внутри train. "
            "Test использован только для финальной оценки."
        ),
    }
    torch.save(checkpoint_payload, checkpoint_file)

    baseline = None
    if baseline_metrics_path().is_file():
        baseline = load_json(baseline_metrics_path())

    summary = {
        "experiment": nn_params.get("experiment_name", "Credit_Scoring_MLP"),
        "python_paths": {
            "checkpoint": str(checkpoint_file),
            "preprocessor": str(preprocessor_file),
            "metadata": str(nn_metadata_path()),
        },
        "data": {
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "fit_rows": int(len(x_fit_raw)),
            "val_rows": int(len(x_val_raw)),
            "target": target,
            "test_size": float(prepare["test_size"]),
            "random_state": int(prepare["random_state"]),
        },
        "model_config": model_config,
        "training": {
            "best_epoch_by_val": best_epoch,
            "best_val_roc_auc": best_val_auc,
            "retrain_epochs_on_full_train": retrain_epochs,
            "history": history,
            "threads": threads,
            "device": str(device),
            "seed": seed,
        },
        "metrics": {
            "train": train_metrics,
            "test": test_metrics,
            "selection_note": (
                "Early stopping по val ROC-AUC (val из train). "
                "Test метрики — только отчёт."
            ),
        },
        "baseline_random_forest": baseline,
        "comparison_note": (
            "Сравнение с RF baseline честное: метрики RF исторические из исходного "
            "проекта; метрики MLP измерены этим запуском."
        ),
    }
    dump_json(nn_metadata_path(), summary)
    dump_json(artifacts_dir() / "nn_metrics.json", summary)
    dump_json(artifacts_dir() / "nn_training_history.json", {"history": history})

    print(f"Checkpoint: {checkpoint_file}")
    print(f"Preprocessor: {preprocessor_file}")
    print(f"Best val ROC-AUC: {best_val_auc:.4f} @ epoch {best_epoch}")
    print("Test metrics:")
    for name in ("roc_auc", "pr_auc", "precision", "recall", "f1", "accuracy"):
        print(f"  {name}: {test_metrics[name]:.4f}")
    if baseline and "metrics" in baseline:
        rf_auc = baseline["metrics"].get("roc_auc")
        if rf_auc is not None:
            delta = test_metrics["roc_auc"] - float(rf_auc)
            print(f"Δ test ROC-AUC vs RF baseline: {delta:+.4f}")
    return summary


def main() -> None:
    train_mlp(device_name="cpu")


if __name__ == "__main__":
    main()
