"""CLI for Stage 6: data drift, concept-drift signal, offline A/B, demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.monitoring.ab_testing import (
    compare_models_offline,
    rollback_to_champion_plan,
    write_model_registry,
)
from src.monitoring.concept_drift import run_concept_drift_check
from src.monitoring.data_drift import run_data_drift
from src.monitoring.reports import monitoring_dir, utc_now_iso, write_report
from src.monitoring.thresholds import load_stage6_thresholds
from src.schema import TARGET_COLUMN, detect_target


def _read_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _resolve_target(df: pd.DataFrame, preferred: str | None) -> str | None:
    if preferred and preferred in df.columns:
        return preferred
    try:
        return detect_target(df.columns, preferred=preferred)
    except ValueError:
        return None


def cmd_data_drift(args: argparse.Namespace) -> int:
    reference = _read_frame(Path(args.reference))
    current = _read_frame(Path(args.current))
    target = args.target
    result = run_data_drift(
        reference,
        current,
        target_column=target,
        save_html=not args.no_html,
        output_name=args.name,
    )
    print(
        f"data_drift_detected={result.get('data_drift_detected')} "
        f"share={result.get('drift_share')} report={result.get('report_path')}"
    )
    return 0


def cmd_concept_drift(args: argparse.Namespace) -> int:
    ref = _read_frame(Path(args.reference))
    cur = _read_frame(Path(args.current))
    y_col = args.y_column
    p_col = args.proba_column
    for frame, label in ((ref, "reference"), (cur, "current")):
        if y_col not in frame.columns:
            raise SystemExit(f"{label} missing y column {y_col}")
        if p_col not in frame.columns:
            raise SystemExit(f"{label} missing probability column {p_col}")
    result = run_concept_drift_check(
        reference_y=ref[y_col],
        reference_proba=ref[p_col],
        current_y=cur[y_col],
        current_proba=cur[p_col],
        threshold=args.threshold,
        model_version=args.model_version,
        output_name=args.name,
    )
    print(
        f"degradation_signal={result.get('degradation_signal')} "
        f"status={result.get('status')} report={result.get('report_path')}"
    )
    return 0


def cmd_ab_offline(args: argparse.Namespace) -> int:
    frame = _read_frame(Path(args.data))
    for col in (args.y_column, args.champion_proba, args.challenger_proba):
        if col not in frame.columns:
            raise SystemExit(f"Missing column: {col}")
    cfg = load_stage6_thresholds().get("versions", {})
    result = compare_models_offline(
        frame[args.y_column],
        frame[args.champion_proba],
        frame[args.challenger_proba],
        champion_version=args.champion_version or cfg.get("champion", "champion"),
        challenger_version=args.challenger_version
        or cfg.get("challenger", "challenger"),
        threshold=args.threshold,
        output_name=args.name,
        n_bootstrap=args.bootstrap,
    )
    print(
        f"status={result.get('status')} "
        f"challenger_favored={result.get('challenger_statistically_favored')} "
        f"report={result.get('report_path')}"
    )
    return 0


def _make_demo_frames(seed: int = 7) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    n = 120
    # Reference / current without drift.
    stable = pd.DataFrame(
        {
            "LIMIT_BAL": rng.normal(150000, 40000, n),
            "AGE": rng.integers(21, 65, n),
            "SEX": rng.choice([1, 2], n),
            "EDUCATION": rng.choice([1, 2, 3], n),
            "MARRIAGE": rng.choice([1, 2], n),
            "PAY_0": rng.integers(-1, 3, n),
            "BILL_AMT1": rng.normal(40000, 15000, n),
            "PAY_AMT1": rng.normal(5000, 2000, n),
            TARGET_COLUMN: rng.integers(0, 2, n),
        }
    )
    drifted = stable.copy()
    drifted["LIMIT_BAL"] = drifted["LIMIT_BAL"] + 80000
    drifted["AGE"] = drifted["AGE"] + 8
    drifted["EDUCATION"] = rng.choice([1, 2, 3, 4, 5], n)

    # Labeled quality demo: good reference, degraded current scores.
    y_ref = rng.integers(0, 2, 80)
    # Correlated scores for reference.
    proba_ref = np.clip(0.2 + 0.6 * y_ref + rng.normal(0, 0.08, 80), 0.01, 0.99)
    y_cur = rng.integers(0, 2, 80)
    proba_cur = np.clip(0.45 + 0.1 * y_cur + rng.normal(0, 0.15, 80), 0.01, 0.99)

    # Offline A/B same holdout: champion noisier, challenger clearer separation.
    y_ab = rng.integers(0, 2, 100)
    noise = rng.normal(0, 0.18, 100)
    champ = np.clip(0.35 + 0.35 * y_ab + noise, 0.01, 0.99)
    chall = np.clip(0.15 + 0.7 * y_ab + noise * 0.35, 0.01, 0.99)
    ab_df = pd.DataFrame(
        {
            "y": y_ab,
            "champion_proba": champ,
            "challenger_proba": chall,
        }
    )
    return {
        "stable": stable,
        "drifted": drifted,
        "y_ref": y_ref,
        "proba_ref": proba_ref,
        "y_cur": y_cur,
        "proba_cur": proba_cur,
        "ab_df": ab_df,
    }


def cmd_demo(_args: argparse.Namespace) -> int:
    """Generate synthetic Stage 6 artifacts (no real credit PII)."""
    demo = _make_demo_frames()
    cfg = load_stage6_thresholds()

    no_drift = run_data_drift(
        demo["stable"],
        demo["stable"].sample(frac=1.0, random_state=1).reset_index(drop=True),
        target_column=TARGET_COLUMN,
        save_html=False,
        output_name="demo_data_drift_none",
    )
    with_drift = run_data_drift(
        demo["stable"],
        demo["drifted"],
        target_column=TARGET_COLUMN,
        save_html=True,
        output_name="demo_data_drift_shift",
    )
    concept = run_concept_drift_check(
        reference_y=demo["y_ref"],
        reference_proba=demo["proba_ref"],
        current_y=demo["y_cur"],
        current_proba=demo["proba_cur"],
        model_version=cfg.get("versions", {}).get("champion"),
        output_name="demo_concept_signal",
    )
    ab = compare_models_offline(
        demo["ab_df"]["y"],
        demo["ab_df"]["champion_proba"],
        demo["ab_df"]["challenger_proba"],
        champion_version=cfg.get("versions", {}).get("champion", "champion"),
        challenger_version=cfg.get("versions", {}).get("challenger", "challenger"),
        output_name="demo_ab_offline",
        n_bootstrap=100,
    )
    # Experiment registry only — never production models/model_registry.json.
    demo_registry = monitoring_dir() / "demo_model_registry.json"
    registry = write_model_registry(
        {"demo": True, "synthetic_only": True},
        registry_path=demo_registry,
    )
    rollback = rollback_to_champion_plan()
    summary = {
        "demo": True,
        "synthetic_only": True,
        "no_real_pii": True,
        "generated_at_utc": utc_now_iso(),
        "auto_promote": False,
        "data_drift_none": {
            "detected": no_drift.get("data_drift_detected"),
            "share": no_drift.get("drift_share"),
            "report": no_drift.get("report_path"),
        },
        "data_drift_shift": {
            "detected": with_drift.get("data_drift_detected"),
            "share": with_drift.get("drift_share"),
            "report": with_drift.get("report_path"),
            "html": with_drift.get("evidently_html"),
        },
        "concept_signal": {
            "degradation_signal": concept.get("degradation_signal"),
            "confirmed_concept_drift": concept.get("confirmed_concept_drift"),
            "report": concept.get("report_path"),
        },
        "ab_offline": {
            "challenger_favored": ab.get("challenger_statistically_favored"),
            "deltas": ab.get("metric_deltas_challenger_minus_champion"),
            "report": ab.get("report_path"),
        },
        "model_registry": str(registry),
        "production_registry_untouched": True,
        "rollback_plan": rollback.get("report_path"),
    }
    path = write_report("demo_summary", summary)
    print(f"Stage 6 demo summary: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.monitoring.cli",
        description="Stage 6 monitoring: data drift, quality signal, A/B offline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_dd = sub.add_parser("data-drift", help="Evidently data drift analysis")
    p_dd.add_argument("--reference", required=True)
    p_dd.add_argument("--current", required=True)
    p_dd.add_argument("--target", default=None)
    p_dd.add_argument("--name", default="data_drift")
    p_dd.add_argument("--no-html", action="store_true")
    p_dd.set_defaults(func=cmd_data_drift)

    p_cd = sub.add_parser(
        "concept-drift", help="Labeled quality degradation signal (not auto-proof)"
    )
    p_cd.add_argument("--reference", required=True)
    p_cd.add_argument("--current", required=True)
    p_cd.add_argument("--y-column", default="y")
    p_cd.add_argument("--proba-column", default="proba")
    p_cd.add_argument("--threshold", type=float, default=0.5)
    p_cd.add_argument("--model-version", default=None)
    p_cd.add_argument("--name", default="concept_drift")
    p_cd.set_defaults(func=cmd_concept_drift)

    p_ab = sub.add_parser("ab-offline", help="Same-holdout champion vs challenger")
    p_ab.add_argument("--data", required=True)
    p_ab.add_argument("--y-column", default="y")
    p_ab.add_argument("--champion-proba", default="champion_proba")
    p_ab.add_argument("--challenger-proba", default="challenger_proba")
    p_ab.add_argument("--champion-version", default=None)
    p_ab.add_argument("--challenger-version", default=None)
    p_ab.add_argument("--threshold", type=float, default=0.5)
    p_ab.add_argument("--bootstrap", type=int, default=200)
    p_ab.add_argument("--name", default="ab_offline")
    p_ab.set_defaults(func=cmd_ab_offline)

    p_demo = sub.add_parser("demo", help="Synthetic Stage 6 demo artifacts")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
