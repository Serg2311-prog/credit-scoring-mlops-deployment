"""Generate synthetic DVC-tracked demo CSV (no real credit/PII rows)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.data.synthetic import make_synthetic_frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--rows", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = make_synthetic_frame(int(args.rows), seed=int(args.seed))
    frame.to_csv(path, index=False)
    print(f"wrote {path} rows={len(frame)} synthetic_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
