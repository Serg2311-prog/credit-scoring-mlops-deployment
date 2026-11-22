"""Render local Kustomize overlay patched for CI synthetic artifacts.

Production ConfigMap keeps EXPECTED_INPUT_DIM=47.
Kind smoke on GitHub builds synthetic ONNX/preprocessor (dim != 47) and must
align ConfigMap EXPECTED_INPUT_DIM + MODEL_VERSION before apply, otherwise
readiness stays 503 and rollout times out.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_marker(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("synthetic"):
        raise SystemExit(f"Marker is not synthetic: {path}")
    if "input_dim" not in data or "model_version" not in data:
        raise SystemExit(f"Marker missing input_dim/model_version: {path}")
    return data


def _patch_configmap_data(docs: list[dict], input_dim: int, model_version: str) -> None:
    found = False
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") != "ConfigMap":
            continue
        meta = doc.get("metadata") or {}
        if meta.get("name") != "credit-scoring-api-config":
            continue
        data = doc.setdefault("data", {})
        data["EXPECTED_INPUT_DIM"] = str(int(input_dim))
        data["MODEL_VERSION"] = str(model_version)
        found = True
    if not found:
        raise SystemExit("credit-scoring-api-config ConfigMap not found in render")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overlay",
        type=Path,
        default=ROOT / "k8s" / "overlays" / "local",
    )
    parser.add_argument(
        "--marker",
        type=Path,
        default=ROOT / "models" / "CI_SYNTHETIC_ARTIFACTS.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "ci" / "kustomize-kind-smoke.yaml",
    )
    args = parser.parse_args()

    if not args.marker.is_file():
        raise SystemExit(f"Missing synthetic marker: {args.marker}")

    marker = _load_marker(args.marker)
    input_dim = int(marker["input_dim"])
    model_version = str(marker["model_version"])
    if input_dim == 47:
        print(
            "WARNING: synthetic marker reports input_dim=47 "
            "(same as production ConfigMap default)",
            file=sys.stderr,
        )

    rendered = subprocess.check_output(
        ["kubectl", "kustomize", str(args.overlay)],
        text=True,
    )

    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML required to patch manifests") from exc

    docs = list(yaml.safe_load_all(rendered))
    _patch_configmap_data(docs, input_dim=input_dim, model_version=model_version)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        yaml.safe_dump_all(docs, handle, sort_keys=False)

    print(
        f"Wrote {args.output} with EXPECTED_INPUT_DIM={input_dim} "
        f"MODEL_VERSION={model_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
