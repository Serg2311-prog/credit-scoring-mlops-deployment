"""Split/validate DVC demo dataset into train/test + meta."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from src.data.validation import validate_dataframe
from src.schema import TARGET_COLUMN, detect_target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.25)
    args = parser.parse_args()

    src = Path(args.input)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(src)
    validated = validate_dataframe(frame)
    target = detect_target(validated.columns, preferred=TARGET_COLUMN)
    train_df, test_df = train_test_split(
        validated,
        test_size=float(args.test_size),
        random_state=int(args.seed),
        stratify=validated[target],
    )
    train_path = out / "train_demo.csv"
    test_path = out / "test_demo.csv"
    meta_path = out / "demo_meta.json"
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)
    meta = {
        "source": str(src).replace("\\", "/"),
        "target": target,
        "rows_raw": int(len(validated)),
        "rows_train": int(len(train_df)),
        "rows_test": int(len(test_df)),
        "seed": int(args.seed),
        "synthetic_only": True,
        "no_real_pii": True,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
