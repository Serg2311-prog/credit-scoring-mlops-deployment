"""Same-holdout champion scoring — no historical-metric shortcut as equal comparison."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.synthetic import make_synthetic_frame
from src.retraining.champion import try_make_champion_scorer
from src.retraining.evaluation import evaluate_candidate
from src.retraining.trainer import train_candidate
from src.schema import TARGET_COLUMN


def test_try_make_champion_scorer_or_none():
    scorer = try_make_champion_scorer()
    # Production artifacts may or may not be present in CI; both are valid.
    assert scorer is None or callable(scorer)


def test_evaluate_without_scorer_needs_review_not_fake_deltas(tmp_path: Path):
    frame = make_synthetic_frame(100, seed=3)
    directory = tmp_path / "run"
    directory.mkdir()
    meta = train_candidate(frame, TARGET_COLUMN, run_directory=directory)
    holdout = frame.sample(frac=0.3, random_state=3)
    result = evaluate_candidate(
        holdout,
        TARGET_COLUMN,
        candidate_meta=meta,
        run_directory=directory,
        champion_scorer=None,
    )
    assert result["auto_promote"] is False
    assert (
        result["deltas_candidate_minus_champion"] is None
        or result["champion_status"] != "scored_on_holdout"
    )
    if result["champion_status"] != "scored_on_holdout":
        assert result["status"] in {"needs_review", "rejected"}
        if result["status"] == "needs_review":
            assert any("same holdout" in r.lower() for r in result["reasons"])


def test_evaluate_same_holdout_when_scorer_available(tmp_path: Path):
    scorer = try_make_champion_scorer()
    if scorer is None:
        pytest.skip("production ONNX/preprocessor not loadable in this environment")
    frame = make_synthetic_frame(120, seed=5)
    directory = tmp_path / "run"
    directory.mkdir()
    meta = train_candidate(frame, TARGET_COLUMN, run_directory=directory)
    holdout = frame.sample(frac=0.35, random_state=5)
    result = evaluate_candidate(
        holdout,
        TARGET_COLUMN,
        candidate_meta=meta,
        run_directory=directory,
        champion_scorer=scorer,
    )
    assert result["auto_promote"] is False
    assert result["champion_status"] == "scored_on_holdout"
    assert result["candidate_metrics"] is not None
    assert result["champion_metrics"] is not None
    assert set(result["candidate_metrics"].keys()) >= {
        "roc_auc",
        "pr_auc",
        "f1",
        "precision",
        "recall",
        "accuracy",
    }
    assert result["deltas_candidate_minus_champion"] is not None
    # Do not require candidate superiority — accepted | needs_review | rejected all OK
    assert result["status"] in {"accepted", "needs_review", "rejected"}
