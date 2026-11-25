"""Online A/B defaults and challenger failure handling (no Docker)."""

from __future__ import annotations

from src.monitoring.ab_router import decide_route
from src.monitoring.ab_testing import assign_ab_group


def test_ab_default_disabled_always_champion_even_at_100_percent_share():
    d = decide_route(
        unit_id="u-1",
        ab_enabled=False,
        challenger_share=1.0,
        hash_salt="s",
        champion_version="champ",
        challenger_version="chall",
    )
    assert d.ab_group == "champion"
    assert d.model_version == "champ"


def test_assignment_deterministic_for_same_id():
    a = assign_ab_group("client-42", challenger_share=0.3, salt="block81")
    b = assign_ab_group("client-42", challenger_share=0.3, salt="block81")
    assert a == b


def test_settings_ab_disabled_by_default():
    from src.api.settings import Settings

    s = Settings()
    assert s.ab_enabled is False
