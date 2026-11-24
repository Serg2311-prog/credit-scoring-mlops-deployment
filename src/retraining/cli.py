"""CLI for Stage 7 retraining checks (Windows-friendly, no Airflow required)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from src.config import dump_json
from src.data.synthetic import make_synthetic_frame
from src.retraining.config import load_retraining_config
from src.retraining.data_validation import check_input_data
from src.retraining.demo_data import prepare_demo_input
from src.retraining.exceptions import (
    DataValidationFailed,
    TriggerSkip,
    TriggerUnavailable,
)
from src.retraining.pipeline import dry_run_pipeline, run_retraining_pipeline
from src.retraining.triggers import evaluate_triggers


def cmd_prepare_demo(args: argparse.Namespace) -> int:
    meta = prepare_demo_input(
        output_path=Path(args.output) if args.output else None,
        rows=int(args.rows),
        seed=int(args.seed),
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        result = check_input_data(Path(args.input))
    except DataValidationFailed as exc:
        print(f"VALIDATION_FAILED: {exc}")
        return 2
    payload = {k: v for k, v in result.items() if k != "validated_frame"}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_baseline_input(args: argparse.Namespace) -> int:
    from src.retraining.new_data import save_input_baseline

    payload = save_input_baseline(
        Path(args.input),
        state_file=Path(args.state) if args.state else None,
        note=str(args.note),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_triggers(args: argparse.Namespace) -> int:
    cfg = load_retraining_config()
    ref = pd.read_csv(args.reference) if args.reference else None
    cur = pd.read_csv(args.current) if args.current else None
    decision = evaluate_triggers(
        modes=args.modes,
        force_scheduled=args.force_scheduled,
        input_path=Path(args.input) if args.input else None,
        input_state_path=Path(args.state) if getattr(args, "state", None) else None,
        reference_features=ref,
        current_features=cur,
        cfg=cfg,
        output_path=Path(args.output) if args.output else None,
        save_html=False,
    )
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    if decision["status"] == "triggered":
        return 0
    if decision["status"] == "skipped":
        return 0
    # unavailable / unexpected → non-zero (not silent success)
    return 3


def cmd_dry_run(args: argparse.Namespace) -> int:
    try:
        report = dry_run_pipeline(
            Path(args.input),
            modes=args.modes,
            force_trigger=args.force_scheduled,
            reference_path=Path(args.reference) if args.reference else None,
            current_path=Path(args.current) if args.current else None,
        )
    except TriggerSkip as exc:
        print(f"SKIPPED: {exc}")
        return 0
    except TriggerUnavailable as exc:
        print(f"TRIGGER_UNAVAILABLE: {exc}")
        return 3
    except DataValidationFailed as exc:
        print(f"VALIDATION_FAILED: {exc}")
        return 2
    print(
        json.dumps(
            {k: report[k] for k in report if k != "candidate"}, indent=2, default=str
        )
    )
    print(f"report={report.get('report_path')}")
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    try:
        report = run_retraining_pipeline(
            Path(args.input),
            modes=args.modes,
            dry_run=args.dry_run,
            force_trigger=True,
            registry_path=Path(args.registry) if args.registry else None,
        )
    except TriggerSkip as exc:
        print(f"SKIPPED: {exc}")
        return 0
    except TriggerUnavailable as exc:
        print(f"TRIGGER_UNAVAILABLE: {exc}")
        return 3
    except DataValidationFailed as exc:
        print(f"VALIDATION_FAILED: {exc}")
        return 2
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "status": report["status"],
                "dry_run": report["dry_run"],
                "auto_promote": report["auto_promote"],
                "report_path": report.get("report_path"),
                "registry": report.get("registry"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    path = Path(args.run_dir) / "retraining_report.json"
    if not path.is_file():
        print(f"Report not found: {path}")
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Synthetic end-to-end dry-run (no production mutation)."""
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame = make_synthetic_frame(120, seed=7)
    csv_path = out / "synthetic_retrain_input.csv"
    frame.to_csv(csv_path, index=False)
    report = dry_run_pipeline(csv_path, modes="scheduled", force_trigger=True)
    summary = {
        "demo": True,
        "input": str(csv_path),
        "run_id": report["run_id"],
        "status": report["status"],
        "auto_promote": False,
        "report_path": report.get("report_path"),
    }
    dump_json(out / "stage7_demo_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.retraining.cli",
        description="Stage 7 retraining CLI (no Airflow required)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "prepare-demo-input",
        help="Write synthetic DAG/CLI input CSV under artifacts/retraining/demo_input",
    )
    p.add_argument("--output", default=None)
    p.add_argument("--rows", type=int, default=120)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=cmd_prepare_demo)

    p = sub.add_parser("validate-data", help="Validate input CSV/Parquet")
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser(
        "baseline-input-state",
        help="Save input CSV fingerprint baseline for new_data trigger",
    )
    p.add_argument("--input", required=True)
    p.add_argument("--state", default=None, help="Optional state JSON path")
    p.add_argument("--note", default="baseline")
    p.set_defaults(func=cmd_baseline_input)

    p = sub.add_parser("check-triggers", help="Evaluate retraining triggers")
    p.add_argument("--modes", default="scheduled")
    p.add_argument("--input", default=None, help="Input CSV for new_data fingerprint")
    p.add_argument("--state", default=None, help="Fingerprint state JSON path")
    p.add_argument("--reference", default=None)
    p.add_argument("--current", default=None)
    p.add_argument("--force-scheduled", action="store_true")
    p.add_argument("--output", default=None)
    p.set_defaults(func=cmd_triggers)

    p = sub.add_parser("dry-run", help="Full pipeline dry-run (no prod registry)")
    p.add_argument("--input", required=True)
    p.add_argument("--modes", default="scheduled")
    p.add_argument("--reference", default=None)
    p.add_argument("--current", default=None)
    p.add_argument("--force-scheduled", action="store_true")
    p.set_defaults(func=cmd_dry_run)

    p = sub.add_parser("train-candidate", help="Train/evaluate/register candidate")
    p.add_argument("--input", required=True)
    p.add_argument("--modes", default="scheduled")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--registry", default=None, help="Optional non-prod registry path")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("generate-report", help="Print existing run report")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("demo", help="Synthetic dry-run demo")
    p.add_argument(
        "--output-dir",
        default=str(Path("artifacts") / "retraining" / "demo"),
    )
    p.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
