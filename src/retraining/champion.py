"""Score production champion on the same holdout as the candidate."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.models.preprocessing import preprocessor_input_dim, transform_features
from src.retraining.exceptions import ChampionUnavailable
from src.schema import RAW_FEATURE_COLUMNS, TARGET_COLUMN

ChampionScorer = Callable[[pd.DataFrame], np.ndarray]


def default_champion_paths() -> tuple[Path, Path]:
    root = PROJECT_ROOT
    return (
        root / "models" / "credit_scoring_nn.onnx",
        root / "models" / "preprocessor.joblib",
    )


def make_onnx_champion_scorer(
    *,
    model_path: Path | None = None,
    preprocessor_path: Path | None = None,
    target: str = TARGET_COLUMN,
) -> ChampionScorer:
    """
    Build a scorer that applies the production preprocessor + ONNX champion
    to an arbitrary holdout frame (same rows/target as candidate eval).
    """
    onnx_path, pre_path = default_champion_paths()
    model_path = Path(model_path) if model_path else onnx_path
    preprocessor_path = Path(preprocessor_path) if preprocessor_path else pre_path
    if not model_path.is_file():
        raise ChampionUnavailable(f"Champion ONNX missing: {model_path}")
    if not preprocessor_path.is_file():
        raise ChampionUnavailable(f"Champion preprocessor missing: {preprocessor_path}")

    try:
        import onnxruntime as ort
    except ImportError as exc:  # pragma: no cover
        raise ChampionUnavailable(
            "onnxruntime is required to score the production champion on holdout"
        ) from exc

    preprocessor = joblib.load(preprocessor_path)
    pre_dim = int(preprocessor_input_dim(preprocessor))
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(model_path),
        sess_options=so,
        providers=["CPUExecutionProvider"],
    )
    inputs = session.get_inputs()
    if not inputs:
        raise ChampionUnavailable("Champion ONNX has no inputs")
    input_name = inputs[0].name
    shape = inputs[0].shape
    if len(shape) >= 2 and not isinstance(shape[1], str) and shape[1] is not None:
        onnx_dim = int(shape[1])
        if onnx_dim != pre_dim:
            raise ChampionUnavailable(
                f"Champion preprocessor dim {pre_dim} != ONNX dim {onnx_dim}"
            )

    def _score(frame: pd.DataFrame) -> np.ndarray:
        if target in frame.columns:
            x = frame.drop(columns=[target])
        else:
            x = frame
        cols = [c for c in RAW_FEATURE_COLUMNS if c in x.columns]
        if not cols:
            raise ChampionUnavailable("Holdout has no champion feature columns")
        matrix = transform_features(preprocessor, x.loc[:, cols]).astype(np.float32)
        outputs = session.run(None, {input_name: matrix})
        if not outputs:
            raise ChampionUnavailable("Champion ONNX returned no outputs")
        arr = np.asarray(outputs[0], dtype=float)
        if arr.ndim == 2 and arr.shape[1] >= 2:
            return arr[:, 1]
        if arr.ndim == 2 and arr.shape[1] == 1:
            return arr[:, 0]
        if arr.ndim == 1:
            return arr
        raise ChampionUnavailable(f"Unexpected champion ONNX output shape: {arr.shape}")

    return _score


def try_make_champion_scorer(**kwargs: Any) -> ChampionScorer | None:
    """Return scorer or None when artifacts/runtime are incompatible."""
    try:
        return make_onnx_champion_scorer(**kwargs)
    except ChampionUnavailable:
        return None
