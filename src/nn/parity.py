"""Сравнение вероятностей PyTorch и ONNX Runtime на одном preprocessing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from src.config import (
    artifacts_dir,
    dump_json,
    load_params,
    nn_onnx_path,
    processed_dir,
)
from src.models.preprocessing import (
    load_preprocessor,
    preprocessor_metadata,
    transform_features,
)
from src.nn.runtime import (
    configure_cpu_threads,
    load_checkpoint,
    probabilities_from_logits,
)
from src.schema import RAW_FEATURE_COLUMNS, detect_target


def _ort_logits(onnx_path: Path, features: np.ndarray) -> np.ndarray:
    import onnxruntime as ort

    session = ort.InferenceSession(
        str(onnx_path),
        providers=["CPUExecutionProvider"],
    )
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: features.astype(np.float32)})
    return np.asarray(outputs[0], dtype=np.float64).reshape(-1)


def _torch_logits(model, features: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        tensor = torch.from_numpy(features.astype(np.float32))
        logits = model(tensor)
    return logits.detach().cpu().numpy().reshape(-1)


def compare_batches(
    torch_prob: np.ndarray,
    onnx_prob: np.ndarray,
) -> dict[str, float]:
    delta = np.abs(torch_prob - onnx_prob)
    return {
        "mae": float(np.mean(delta)),
        "max_abs": float(np.max(delta)),
        "rmse": float(np.sqrt(np.mean(np.square(delta)))),
        "n": int(len(delta)),
    }


def run_parity(
    onnx_path: Path | None = None,
    batch_sizes: list[int] | None = None,
) -> dict[str, Any]:
    configure_cpu_threads()
    params = load_params()
    nn_params = params["nn"]
    atol = float(nn_params.get("parity_atol", 1e-5))
    mae_atol = float(nn_params.get("parity_mae_atol", 1e-6))
    batch_sizes = batch_sizes or [1, 16, 64, 256]

    model, payload = load_checkpoint(map_location="cpu")
    preprocessor = load_preprocessor()
    feature_contract = preprocessor_metadata(preprocessor)
    onnx_file = onnx_path or nn_onnx_path()
    if not onnx_file.is_file():
        raise FileNotFoundError(f"ONNX не найден: {onnx_file}")

    test_path = processed_dir() / "test.csv"
    if not test_path.is_file():
        raise FileNotFoundError("Нет test.csv для parity-проверки")
    test_df = pd.read_csv(test_path)
    target = detect_target(
        test_df.columns, preferred=params["prepare"]["target_column"]
    )
    # Полный serving-path начинается с сырых колонок, не с готовой матрицы.
    raw_features = test_df.drop(columns=[target])
    missing_raw = [
        col for col in RAW_FEATURE_COLUMNS if col not in raw_features.columns
    ]
    if missing_raw:
        raise ValueError("В raw input нет колонок: " + ", ".join(missing_raw))
    raw_ordered = raw_features.loc[:, list(RAW_FEATURE_COLUMNS)]
    features = transform_features(preprocessor, raw_ordered)
    expected_dim = int(payload.get("input_dim") or model.input_dim)
    if features.shape[1] != expected_dim:
        raise ValueError(
            f"Размерность после preprocessing {features.shape[1]} "
            f"!= checkpoint input_dim {expected_dim}"
        )

    batch_reports = []
    all_ok = True
    for batch_size in batch_sizes:
        if len(features) < batch_size:
            batch = features
            used = len(features)
        else:
            batch = features[:batch_size]
            used = batch_size
        torch_logits = _torch_logits(model, batch)
        ort_logits = _ort_logits(onnx_file, batch)
        torch_prob = probabilities_from_logits(torch_logits)
        ort_prob = probabilities_from_logits(ort_logits)
        stats = compare_batches(torch_prob, ort_prob)
        passed = stats["max_abs"] <= atol and stats["mae"] <= max(mae_atol, atol)
        all_ok = all_ok and passed
        batch_reports.append(
            {
                "batch_size_requested": int(batch_size),
                "batch_size_used": int(used),
                "passed": bool(passed),
                **stats,
            }
        )
        print(
            f"batch={used}: max_abs={stats['max_abs']:.3e} "
            f"mae={stats['mae']:.3e} passed={passed}"
        )

    # Полный test path: raw -> preprocess -> model
    torch_prob_full = probabilities_from_logits(_torch_logits(model, features))
    ort_prob_full = probabilities_from_logits(_ort_logits(onnx_file, features))
    full_stats = compare_batches(torch_prob_full, ort_prob_full)
    full_passed = full_stats["max_abs"] <= atol and full_stats["mae"] <= max(
        mae_atol, atol
    )
    all_ok = all_ok and full_passed

    report = {
        "onnx_path": str(onnx_file),
        "n_test_rows": int(len(features)),
        "parity_atol": atol,
        "parity_mae_atol": mae_atol,
        "pipeline": (
            "raw CSV columns (RAW_FEATURE_COLUMNS order) -> "
            "preprocessor.joblib (FeatureEngineer+ColumnTransformer) -> "
            "PyTorch/ONNX logits -> sigmoid"
        ),
        "verifies_full_raw_path": True,
        "raw_feature_columns": list(RAW_FEATURE_COLUMNS),
        "feature_contract": feature_contract,
        "batches": batch_reports,
        "full_test": {"passed": bool(full_passed), **full_stats},
        "passed": bool(all_ok),
    }
    dump_json(artifacts_dir() / "onnx_parity.json", report)
    print(f"Parity overall passed={all_ok}")
    print(f"Отчёт: {artifacts_dir() / 'onnx_parity.json'}")
    if not all_ok:
        raise SystemExit(1)
    return report


def main() -> None:
    run_parity()


if __name__ == "__main__":
    main()
