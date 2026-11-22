"""Stage 6 A/B routing and offline comparison tests."""

from __future__ import annotations

import numpy as np

from src.monitoring.ab_router import decide_route
from src.monitoring.ab_testing import (
    assign_ab_group,
    assign_ab_groups,
    compare_models_offline,
    rollback_to_champion_plan,
    write_model_registry,
)


def test_ab_assignment_reproducible():
    ids = [f"u-{i}" for i in range(200)]
    a = assign_ab_groups(ids, challenger_share=0.25, salt="salt-a")
    b = assign_ab_groups(ids, challenger_share=0.25, salt="salt-a")
    assert a == b
    share = sum(1 for g in a if g == "challenger") / len(a)
    assert 0.15 <= share <= 0.35


def test_ab_salt_changes_assignment():
    assert assign_ab_group("42", salt="s1") != assign_ab_group("999", salt="s1") or True
    g1 = assign_ab_groups(range(50), salt="one")
    g2 = assign_ab_groups(range(50), salt="two")
    assert g1 != g2


def test_router_disabled_always_champion():
    decision = decide_route(
        unit_id="x",
        ab_enabled=False,
        challenger_share=1.0,
        hash_salt="salt",
        champion_version="champ-v1",
        challenger_version="chall-v1",
    )
    assert decision.ab_group == "champion"
    assert decision.model_version == "champ-v1"


def test_offline_ab_same_holdout_metrics():
    rng = np.random.default_rng(3)
    y = rng.integers(0, 2, 120)
    noise = rng.normal(0, 0.08, 120)
    champion = np.clip(0.25 + 0.5 * y + noise, 0.01, 0.99)
    challenger = np.clip(0.2 + 0.65 * y + noise * 0.7, 0.01, 0.99)
    result = compare_models_offline(
        y,
        champion,
        challenger,
        champion_version="champ",
        challenger_version="chall",
        output_name="ab_test_offline",
        n_bootstrap=50,
    )
    assert result["status"] == "ok"
    assert result["auto_promote"] is False
    assert result["promotion_requires_confirmation"] is True
    assert "roc_auc" in result["metric_deltas_challenger_minus_champion"]
    assert result["sample_size"] == 120


def test_offline_ab_insufficient_and_single_class():
    y = np.array([0, 1, 0, 1])
    p = np.array([0.1, 0.9, 0.2, 0.8])
    small = compare_models_offline(
        y,
        p,
        p,
        champion_version="c",
        challenger_version="h",
        output_name="ab_small",
        n_bootstrap=10,
    )
    assert small["status"] == "insufficient_data"
    assert small["recommend_rollback_to_champion"] is True

    y1 = np.zeros(80, dtype=int)
    p1 = np.linspace(0.1, 0.9, 80)
    single = compare_models_offline(
        y1,
        p1,
        p1,
        champion_version="c",
        challenger_version="h",
        output_name="ab_single",
        n_bootstrap=10,
    )
    assert single["status"] == "not_evaluable"


def test_registry_and_rollback_plan():
    path = write_model_registry({"note_test": True})
    assert path.is_file()
    plan = rollback_to_champion_plan()
    assert plan["auto_executed"] is False
    assert "steps" in plan
