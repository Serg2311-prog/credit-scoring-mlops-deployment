"""Block 4.2: dual pytest/black/flake8 with production artifact hash guards."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = [
    ROOT / "models" / "model_registry.json",
    ROOT / "models" / "credit_scoring_nn.onnx",
    ROOT / "models" / "preprocessor.joblib",
    ROOT / "dvc.lock",
]


def sha256(path: Path) -> str:
    if not path.is_file():
        return "ABSENT"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot() -> dict[str, str]:
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p) for p in ARTIFACTS}


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> int:
    py = sys.executable
    before = snapshot()
    print("=== HASHES BEFORE_ALL ===")
    for key, value in before.items():
        print(f"{value}  {key}")

    for pass_no in (1, 2):
        print(f"\n######## PASS {pass_no} / 2 ########", flush=True)
        run([py, "-m", "pytest", "-q", "-m", "not k8s and not e2e"])
        run(
            [
                py,
                "-m",
                "black",
                "--check",
                "src",
                "tests",
                "scripts/ci",
                "airflow_home/dags",
            ]
        )
        run([py, "-m", "flake8", "src", "tests", "scripts/ci", "airflow_home/dags"])
        after = snapshot()
        print(f"=== HASHES AFTER_PASS_{pass_no} ===")
        for key, value in after.items():
            print(f"{value}  {key}")
        for key in before:
            if before[key] != after[key]:
                print(f"CHANGED {key}: {before[key]} -> {after[key]}", file=sys.stderr)
                return 2
        print(f"RUN {pass_no}: all 4 artifacts unchanged", flush=True)

    print("\nDUAL PASS OK — artifacts stable", flush=True)
    run(["git", "diff", "--check"])
    run(["git", "diff", "--", "models/"])
    run(["git", "diff", "--", "dvc.lock"])
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
