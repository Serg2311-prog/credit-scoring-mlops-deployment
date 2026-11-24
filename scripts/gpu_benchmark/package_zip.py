"""Build Colab ZIP with POSIX archive paths (as_posix)."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def add_tree(zf: zipfile.ZipFile, src_dir: Path, arc_prefix: str) -> list[str]:
    paths: list[str] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        # Skip nested out/ dirs relative to package root only
        rel = path.relative_to(src_dir)
        if "out" in rel.parts:
            continue
        arcname = f"{arc_prefix}/{rel.as_posix()}"
        zf.write(path, arcname=arcname)
        paths.append(arcname)
    return paths


def build_package(output_zip: Path) -> dict:
    stage = ROOT / "_stage_pkg"
    if stage.exists():
        shutil.rmtree(stage)
    pkg = stage / "colab_gpu_benchmark"
    (pkg / "models").mkdir(parents=True)
    (pkg / "data").mkdir(parents=True)

    for name in (
        "run_benchmark.py",
        "mlp_model.py",
        "README.md",
        "COLAB_CELLS.md",
        "requirements_colab.txt",
        "experiment_config.json",
    ):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, pkg / name)

    shutil.copy2(REPO / "src" / "nn" / "ort_profiling.py", pkg / "ort_profiling.py")
    shutil.copy2(
        REPO / "models" / "credit_scoring_nn.pt",
        pkg / "models" / "credit_scoring_nn.pt",
    )
    shutil.copy2(
        REPO / "models" / "credit_scoring_nn.onnx",
        pkg / "models" / "credit_scoring_nn.onnx",
    )

    hist_data = REPO / "artifacts" / "block7" / "colab_gpu_benchmark_pkg" / "data"
    shutil.copy2(
        hist_data / "synthetic_features.npy", pkg / "data" / "synthetic_features.npy"
    )
    shutil.copy2(
        hist_data / "synthetic_features_meta.json",
        pkg / "data" / "synthetic_features_meta.json",
    )

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        names = add_tree(zf, pkg, "colab_gpu_benchmark")

    shutil.rmtree(stage)
    bad = [name for name in names if "\\" in name]
    if bad:
        raise RuntimeError(f"Non-POSIX archive paths: {bad}")

    info = {
        "zip": output_zip.as_posix(),
        "entries": names,
        "sha256": hashlib.sha256(output_zip.read_bytes()).hexdigest(),
        "size_bytes": output_zip.stat().st_size,
    }
    (output_zip.with_suffix(".zip.manifest.json")).write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / "artifacts" / "block7" / "colab_gpu_benchmark_hardened.zip",
    )
    args = parser.parse_args()
    print(json.dumps(build_package(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
