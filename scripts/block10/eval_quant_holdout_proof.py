"""Inference-only holdout eval for ONNX FP32 vs INT8 (Block 10.2 proof).

Does not retrain or write production models. Writes JSON under results/block10/.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

import joblib
import numpy as np
import onnxruntime as ort
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.models.preprocessing import transform_features  # noqa: E402
from src.schema import TARGET_COLUMN  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _eval_onnx(path: Path, x: np.ndarray, y: np.ndarray, threshold: float) -> dict:
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0].name
    out = sess.get_outputs()[0].name
    logits: list[np.ndarray] = []
    for i in range(0, len(x), 512):
        logits.append(sess.run([out], {inp: x[i : i + 512]})[0].reshape(-1))
    logits_arr = np.concatenate(logits)
    probs = 1.0 / (1.0 + np.exp(-logits_arr))
    pred = (probs >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred).ravel()
    return {
        "roc_auc": float(roc_auc_score(y, probs)),
        "pr_auc": float(average_precision_score(y, probs)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "accuracy": float(accuracy_score(y, pred)),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
        "probabilities": probs,
    }


def main() -> int:
    threshold = 0.5
    quant_p = ROOT / "models" / "credit_scoring_nn.quant.onnx"
    fp32_p = ROOT / "models" / "credit_scoring_nn.onnx"
    pre_p = ROOT / "models" / "preprocessor.joblib"
    test_p = ROOT / "data" / "processed" / "test.csv"
    out_path = ROOT / "results" / "block10" / "quant_roc_auc_proof_block102.json"

    test = pd.read_csv(test_p)
    y = test[TARGET_COLUMN].astype(int).to_numpy()
    pre = joblib.load(pre_p)
    x = np.asarray(
        transform_features(pre, test.drop(columns=[TARGET_COLUMN])),
        dtype=np.float32,
    )

    fp32 = _eval_onnx(fp32_p, x, y, threshold)
    quant = _eval_onnx(quant_p, x, y, threshold)
    pf = fp32.pop("probabilities")
    pq = quant.pop("probabilities")
    flips = (pf >= threshold).astype(int) != (pq >= threshold).astype(int)

    proof = {
        "block": "10.2",
        "evaluation_mode": "inference_only_no_retrain",
        "reproducible_command": (
            "PYTHONPATH=. python scripts/block10/eval_quant_holdout_proof.py"
        ),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "onnxruntime_version": pkg_version("onnxruntime"),
        "onnxruntime_providers_used": ["CPUExecutionProvider"],
        "model_sha256": {
            "credit_scoring_nn.onnx": _sha256(fp32_p),
            "credit_scoring_nn.quant.onnx": _sha256(quant_p),
            "preprocessor.joblib": _sha256(pre_p),
        },
        "dataset": {
            "raw_filename": "UCI_Credit_Card.csv",
            "holdout_path": "data/processed/test.csv",
            "target_column": TARGET_COLUMN,
            "holdout_n": int(len(y)),
            "positive_rate": float(y.mean()),
            "split": {
                "test_size": 0.2,
                "random_state": 42,
                "stratified": True,
                "source": "params.yaml prepare.*",
            },
        },
        "threshold": threshold,
        "input_dim": int(x.shape[1]),
        "fp32": fp32,
        "quant_int8": quant,
        "fp32_vs_int8": {
            "roc_auc_delta_quant_minus_fp32": quant["roc_auc"] - fp32["roc_auc"],
            "decision_flips": int(flips.sum()),
            "decision_flip_rate": float(flips.mean()),
            "prob_mae": float(np.abs(pq - pf).mean()),
            "prob_max_abs": float(np.abs(pq - pf).max()),
        },
        "historical_snapshots_not_overwritten": {
            "artifacts/onnx_quantization.json_quant_roc_auc": 0.7720294607173503,
            "artifacts/benchmark_cpu.json_quant_roc_auc": 0.7736312001588113,
            "note": (
                "Different historical numbers may relate to ORT/runtime differences; "
                "ORT-version causality is a possible cause, not a controlled fact here."
            ),
        },
        "canonical_quant_roc_auc": quant["roc_auc"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(out_path),
                **{
                    "canonical_quant_roc_auc": proof["canonical_quant_roc_auc"],
                    "onnxruntime_version": proof["onnxruntime_version"],
                    "python_version": proof["python_version"],
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
