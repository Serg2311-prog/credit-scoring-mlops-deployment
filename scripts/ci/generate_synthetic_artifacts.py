"""Generate deterministic CI-only ONNX + preprocessor artifacts.

These artifacts are NOT the production stage-1 model.
They exist only to exercise serving/Docker/K8s contract tests when
models/*.onnx and the UCI CSV are absent from Git.

Usage:
  python scripts/ci/generate_synthetic_artifacts.py
  python scripts/ci/generate_synthetic_artifacts.py --output-dir models
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.synthetic import make_synthetic_frame  # noqa: E402
from src.models.preprocessing import (  # noqa: E402
    fit_preprocessor,
    save_preprocessor,
    transform_features,
)
from src.nn.model import CreditScoringMLP  # noqa: E402
from src.nn.runtime import set_seed  # noqa: E402
from src.schema import RAW_FEATURE_COLUMNS, TARGET_COLUMN  # noqa: E402

MARKER_NAME = "CI_SYNTHETIC_ARTIFACTS.json"
MODEL_VERSION = "ci-synthetic-mlp-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate(output_dir: Path, seed: int = 42, force: bool = False) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    onnx_existing = output_dir / "credit_scoring_nn.onnx"
    prep_existing = output_dir / "preprocessor.joblib"
    marker_existing = output_dir / MARKER_NAME
    if (
        (onnx_existing.is_file() or prep_existing.is_file())
        and not marker_existing.is_file()
        and not force
    ):
        raise SystemExit(
            f"Refusing to overwrite non-synthetic artifacts in {output_dir}. "
            "Pass --force only on ephemeral CI runners."
        )
    set_seed(seed)
    frame = make_synthetic_frame(n=96, seed=seed)
    preprocessor = fit_preprocessor(frame[RAW_FEATURE_COLUMNS])
    features = transform_features(preprocessor, frame[RAW_FEATURE_COLUMNS])
    labels = frame[TARGET_COLUMN].astype(np.float32).to_numpy()

    model = CreditScoringMLP(
        input_dim=int(features.shape[1]),
        hidden_dims=[16, 8],
        dropout=0.0,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
    criterion = torch.nn.BCEWithLogitsLoss()
    x = torch.from_numpy(np.array(features, copy=True))
    y = torch.from_numpy(np.array(labels, copy=True))

    model.train()
    for _ in range(40):
        optimizer.zero_grad()
        loss = criterion(model(x), y)
        loss.backward()
        optimizer.step()
    model.eval()

    onnx_path = output_dir / "credit_scoring_nn.onnx"
    prep_path = output_dir / "preprocessor.joblib"
    dummy = torch.zeros((1, model.input_dim), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        input_names=["features"],
        output_names=["logits"],
        dynamic_axes={"features": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    save_preprocessor(preprocessor, prep_path)

    manifest = {
        "synthetic": True,
        "not_production": True,
        "model_version": MODEL_VERSION,
        "seed": seed,
        "input_dim": int(model.input_dim),
        "hidden_dims": model.hidden_dims,
        "files": {
            "credit_scoring_nn.onnx": {
                "sha256": _sha256(onnx_path),
                "bytes": onnx_path.stat().st_size,
            },
            "preprocessor.joblib": {
                "sha256": _sha256(prep_path),
                "bytes": prep_path.stat().st_size,
            },
        },
        "warning": (
            "CI contract artifacts only. Do not treat as stage-1 production model."
        ),
    }
    marker = output_dir / MARKER_NAME
    marker.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Copy for audit under artifacts/ci as well when writing into models/.
    audit_dir = ROOT / "artifacts" / "ci"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "models",
        help="Directory for onnx + joblib (default: models/)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing non-synthetic artifacts (CI runners only).",
    )
    args = parser.parse_args()
    manifest = generate(args.output_dir.resolve(), seed=args.seed, force=args.force)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
