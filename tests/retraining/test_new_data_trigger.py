"""new_data fingerprint trigger — detect change without force_retrain."""

from __future__ import annotations

from pathlib import Path

from src.data.synthetic import make_synthetic_frame
from src.retraining.new_data import compare_input_to_baseline, save_input_baseline
from src.retraining.triggers import evaluate_triggers


def _write_csv(path: Path, seed: int, rows: int = 80) -> Path:
    make_synthetic_frame(rows, seed=seed).to_csv(path, index=False)
    return path


def test_new_data_unavailable_without_baseline(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "input.csv", seed=1)
    decision = evaluate_triggers(
        modes="new_data",
        input_path=csv_path,
        input_state_path=tmp_path / "missing_state.json",
    )
    assert decision["status"] == "unavailable"
    assert "new_data" in decision["unavailable_modes"]
    assert decision["triggered"] is False


def test_new_data_triggers_on_fingerprint_change(tmp_path: Path):
    state = tmp_path / "state.json"
    baseline_csv = _write_csv(tmp_path / "baseline.csv", seed=11)
    save_input_baseline(baseline_csv, state_file=state, note="unit")
    changed = _write_csv(tmp_path / "changed.csv", seed=99)
    decision = evaluate_triggers(
        modes="new_data",
        input_path=changed,
        input_state_path=state,
    )
    assert decision["status"] == "triggered"
    assert "new_data" in decision["fired_modes"]
    assert any(
        r.get("reason") == "new_data" and r.get("fired") for r in decision["reasons"]
    )


def test_new_data_skips_when_unchanged(tmp_path: Path):
    state = tmp_path / "state.json"
    csv_path = _write_csv(tmp_path / "input.csv", seed=42)
    save_input_baseline(csv_path, state_file=state)
    decision = evaluate_triggers(
        modes="new_data",
        input_path=csv_path,
        input_state_path=state,
    )
    assert decision["status"] == "skipped"
    assert decision["triggered"] is False
    assert decision["fired_modes"] == []


def test_new_data_ignores_force_scheduled_when_mode_not_listed(tmp_path: Path):
    """force_scheduled only applies when 'scheduled' is among requested modes."""
    state = tmp_path / "state.json"
    csv_path = _write_csv(tmp_path / "input.csv", seed=7)
    save_input_baseline(csv_path, state_file=state)
    decision = evaluate_triggers(
        modes="new_data",
        force_scheduled=True,
        input_path=csv_path,
        input_state_path=state,
    )
    assert decision["status"] == "skipped"
    assert "scheduled" not in decision["fired_modes"]
    cmp = compare_input_to_baseline(csv_path, state_file=state)
    assert cmp["status"] == "skipped"


def test_scheduled_without_force_does_not_fire():
    decision = evaluate_triggers(modes="scheduled", force_scheduled=False)
    assert decision["status"] == "skipped"
    assert decision["triggered"] is False
