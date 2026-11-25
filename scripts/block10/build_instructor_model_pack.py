"""Build local instructor_model_pack.zip (never commit)."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    "models/credit_scoring_nn.pt",
    "models/credit_scoring_nn.onnx",
    "models/credit_scoring_nn.quant.onnx",
    "models/preprocessor.joblib",
    "models/model_registry.json",
]
README = """# Instructor model pack

Trusted serialized production artifacts for academic verification only.
Includes ONNX/PyTorch weights and a **joblib** preprocessor. Use only after
verifying provenance and SHA256SUMS.txt against the author's documented hashes.

## Install

1. Clone the repository at the agreed commit (apply remediation if needed).
2. Unpack this ZIP at the repository root (POSIX relative paths inside the archive).
3. Verify checksums: `sha256sum -c SHA256SUMS.txt` (or Windows equivalent).

## Do not

- Commit these binaries to a public remote without policy review.
- Mix with CI synthetic artifacts when validating production parity.
- Load joblib from untrusted sources.

## Smoke check

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -c "from pathlib import Path; import hashlib; print('see SHA256SUMS.txt')"
# Start API and hit /health/ready after installing deps from README.
```

See also `docs/instructor_model_pack.md` in the repository.
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    pack_dir = ROOT / "artifacts" / "submission"
    pack_dir.mkdir(parents=True, exist_ok=True)
    zip_path = pack_dir / "instructor_model_pack.zip"
    staging = pack_dir / "_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    sums: list[str] = []
    for rel in FILES:
        src = ROOT / rel
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        dest.write_bytes(data)
        sums.append(f"{hashlib.sha256(data).hexdigest()}  {rel}")

    (staging / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    (staging / "README.md").write_text(README, encoding="utf-8")

    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(staging).as_posix())

    shutil.rmtree(staging)
    meta = {
        "zip_path": "artifacts/submission/instructor_model_pack.zip",
        "zip_sha256": sha256(zip_path),
        "zip_size_bytes": zip_path.stat().st_size,
        "entries": sums,
    }
    (pack_dir / "instructor_model_pack_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
