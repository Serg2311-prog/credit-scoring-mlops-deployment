"""Dynamic quantization ONNX модели для CPU."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config import (
    artifacts_dir,
    dump_json,
    load_params,
    nn_onnx_path,
    nn_quant_onnx_path,
    processed_dir,
)
from src.models.evaluate import compute_metrics
from src.models.preprocessing import load_preprocessor, transform_features
from src.nn.parity import compare_batches
from src.nn.runtime import configure_cpu_threads, probabilities_from_logits
from src.schema import detect_target


def _ort_probabilities(model_path: Path, features: np.ndarray) -> np.ndarray:
    import onnxruntime as ort

    session = ort.InferenceSession(
        str(model_path),
        providers=["CPUExecutionProvider"],
    )
    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: features.astype(np.float32)})[0]
    return probabilities_from_logits(np.asarray(logits).reshape(-1))


def _quantize_via_ascii_temp(src: Path, dst: Path) -> None:
    """ORT quant пишет *-inferred.onnx рядом и падает на non-ASCII path."""
    from onnxruntime.quantization import QuantType, quantize_dynamic

    with tempfile.TemporaryDirectory(prefix="onnx_quant_") as tmp:
        tmp_dir = Path(tmp)
        src_tmp = tmp_dir / "model.onnx"
        dst_tmp = tmp_dir / "model.quant.onnx"
        shutil.copy2(src, src_tmp)
        quantize_dynamic(
            model_input=str(src_tmp),
            model_output=str(dst_tmp),
            weight_type=QuantType.QInt8,
        )
        if not dst_tmp.is_file():
            raise RuntimeError("quantize_dynamic не создал выходной файл")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst_tmp, dst)


def quantize_onnx(
    source: Path | None = None,
    destination: Path | None = None,
) -> dict[str, Any]:
    configure_cpu_threads()

    params = load_params()
    threshold = float(params["nn"].get("threshold", 0.5))
    src = source or nn_onnx_path()
    dst = destination or nn_quant_onnx_path()
    if not src.is_file():
        raise FileNotFoundError(f"Исходный ONNX не найден: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    # weight-only dynamic quantization for MatMul/Gemm on CPU
    _quantize_via_ascii_temp(src, dst)

    test_path = processed_dir() / "test.csv"
    if not test_path.is_file():
        raise FileNotFoundError("Нет test.csv для оценки quantized модели")
    test_df = pd.read_csv(test_path)
    target = detect_target(
        test_df.columns, preferred=params["prepare"]["target_column"]
    )
    y_true = test_df[target].astype(int).to_numpy()
    features = transform_features(load_preprocessor(), test_df.drop(columns=[target]))

    fp32_prob = _ort_probabilities(src, features)
    quant_prob = _ort_probabilities(dst, features)
    fp32_metrics = compute_metrics(y_true, fp32_prob, threshold=threshold)
    quant_metrics = compute_metrics(y_true, quant_prob, threshold=threshold)
    delta = compare_batches(fp32_prob, quant_prob)

    fp32_pred = (fp32_prob >= threshold).astype(int)
    quant_pred = (quant_prob >= threshold).astype(int)
    flips = fp32_pred != quant_pred
    n_rows = int(len(fp32_pred))
    n_flips = int(flips.sum())
    classification_impact = {
        "threshold": threshold,
        "n_rows": n_rows,
        "n_decision_flips": n_flips,
        "decision_flip_rate": float(n_flips / max(n_rows, 1)),
        "flips_0_to_1": int(((fp32_pred == 0) & (quant_pred == 1)).sum()),
        "flips_1_to_0": int(((fp32_pred == 1) & (quant_pred == 0)).sum()),
        "probability_mean_abs_delta": delta["mae"],
        "probability_max_abs_delta": delta["max_abs"],
        "probability_rmse": delta["rmse"],
    }

    report = {
        "method": "onnxruntime.quantization.quantize_dynamic",
        "weight_type": "QInt8",
        "source_onnx": str(src),
        "quantized_onnx": str(dst),
        "source_size_bytes": src.stat().st_size,
        "quantized_size_bytes": dst.stat().st_size,
        "size_reduction_ratio": float(dst.stat().st_size / max(src.stat().st_size, 1)),
        "probability_delta_vs_fp32_onnx": delta,
        "classification_impact": classification_impact,
        "metrics": {
            "onnx_fp32": fp32_metrics,
            "onnx_quantized": quant_metrics,
        },
        "decision_note": (
            "Quantized модель не объявляется лучшей без сравнения "
            "latency/size/metrics. См. benchmark и docs/model_benchmark.md."
        ),
    }
    dump_json(artifacts_dir() / "onnx_quantization.json", report)
    print(f"Quantized ONNX: {dst}")
    print(
        f"Size: {report['source_size_bytes']} -> {report['quantized_size_bytes']} "
        f"({report['size_reduction_ratio']:.3f}x)"
    )
    print(
        "ROC-AUC fp32/quant: "
        f"{fp32_metrics['roc_auc']:.4f} / {quant_metrics['roc_auc']:.4f}"
    )
    print("Prob delta max_abs/mae: " f"{delta['max_abs']:.3e} / {delta['mae']:.3e}")
    print(
        "Decision flips: "
        f"{n_flips}/{n_rows} ({classification_impact['decision_flip_rate']:.4%})"
    )
    return report


def main() -> None:
    quantize_onnx()


if __name__ == "__main__":
    main()
