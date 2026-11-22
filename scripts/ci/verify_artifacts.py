"""Verify local model artifacts and classify synthetic vs production.

Exit codes:
  0 — artifacts present and consistent
  2 — artifacts missing
  3 — synthetic marker indicates CI-only artifacts (ok for CI, not production)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "models"
MARKER = "CI_SYNTHETIC_ARTIFACTS.json"
REQUIRED = ("credit_scoring_nn.onnx", "preprocessor.joblib")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Accept CI synthetic artifacts (default: warn/exit 3 if synthetic).",
    )
    args = parser.parse_args()
    target = args.dir.resolve()

    missing = [name for name in REQUIRED if not (target / name).is_file()]
    if missing:
        print(f"MISSING artifacts in {target}: {missing}")
        return 2

    marker_path = target / MARKER
    if marker_path.is_file():
        manifest = json.loads(marker_path.read_text(encoding="utf-8"))
        print(json.dumps({"status": "synthetic", "manifest": manifest}, indent=2))
        if args.allow_synthetic:
            return 0
        print(
            "Artifacts are CI-synthetic, not production stage-1 weights.",
            file=sys.stderr,
        )
        return 3

    print(
        json.dumps(
            {
                "status": "present_no_synthetic_marker",
                "dir": str(target),
                "files": REQUIRED,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
