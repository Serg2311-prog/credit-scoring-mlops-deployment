"""Render a Kustomize overlay with immutable image tags or digests."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _split_ref(ref: str) -> tuple[str, str | None, str | None]:
    """Return (name, tag, digest)."""
    if "@sha256:" in ref:
        name, digest = ref.split("@", 1)
        return name, None, digest
    if ":" in ref.rsplit("/", 1)[-1]:
        name, tag = ref.rsplit(":", 1)
        return name, tag, None
    raise SystemExit(f"Image ref must include :tag or @sha256:digest — got {ref}")


def _image_entry(logical: str, ref: str) -> dict:
    name, tag, digest = _split_ref(ref)
    entry: dict = {"name": logical, "newName": name}
    if digest:
        entry["digest"] = digest
    else:
        entry["newTag"] = tag
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--models-image", required=True)
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "ci" / "kustomize-cd-render.yaml",
    )
    parser.add_argument("--marker", type=Path, default=None)
    args = parser.parse_args()

    overlay = args.overlay.resolve()
    if not overlay.is_dir():
        raise SystemExit(f"Overlay not found: {overlay}")

    with tempfile.TemporaryDirectory(prefix="kustomize-cd-") as tmp:
        tmp_path = Path(tmp)
        # Copy whole k8s tree so nested overlays resolve without absolute paths.
        k8s_src = ROOT / "k8s"
        k8s_dst = tmp_path / "k8s"
        shutil.copytree(k8s_src, k8s_dst)
        rel = overlay.relative_to(k8s_src.resolve())
        work_overlay = k8s_dst / rel
        wrap = tmp_path / "kustomization.yaml"
        payload = {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": [f"k8s/{rel.as_posix()}"],
            "images": [
                _image_entry("credit-scoring-api", args.api_image),
                _image_entry("credit-scoring-models", args.models_image),
                _image_entry("credit-scoring-frontend", args.frontend_image),
            ],
        }
        wrap.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        # Silence unused (kept for clarity / future patches).
        _ = work_overlay
        rendered = subprocess.check_output(
            ["kubectl", "kustomize", str(tmp_path)],
            text=True,
        )

        if args.marker and args.marker.is_file():
            marker = json.loads(args.marker.read_text(encoding="utf-8"))
            docs = list(yaml.safe_load_all(rendered))
            for doc in docs:
                if not isinstance(doc, dict) or doc.get("kind") != "ConfigMap":
                    continue
                if (doc.get("metadata") or {}).get(
                    "name"
                ) != "credit-scoring-api-config":
                    continue
                data = doc.setdefault("data", {})
                if "input_dim" in marker:
                    data["EXPECTED_INPUT_DIM"] = str(int(marker["input_dim"]))
                if "model_version" in marker:
                    data["MODEL_VERSION"] = str(marker["model_version"])
            chunks: list[str] = []
            for doc in docs:
                if doc is None:
                    continue
                chunks.append(yaml.safe_dump(doc, sort_keys=False))
            rendered = "---\n".join(chunks)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
