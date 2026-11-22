"""Optional A/B routing helpers for the inference API (disabled by default)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.monitoring.ab_testing import GroupName, assign_ab_group


@dataclass(frozen=True)
class AbRouteDecision:
    ab_group: GroupName
    model_version: str
    model_path_key: str  # "champion" | "challenger"


def decide_route(
    *,
    unit_id: str | int,
    ab_enabled: bool,
    challenger_share: float,
    hash_salt: str,
    champion_version: str,
    challenger_version: str,
) -> AbRouteDecision:
    """When A/B is disabled, always return champion (stable production contract)."""
    if not ab_enabled:
        return AbRouteDecision(
            ab_group="champion",
            model_version=champion_version,
            model_path_key="champion",
        )
    group = assign_ab_group(unit_id, challenger_share=challenger_share, salt=hash_salt)
    if group == "challenger":
        return AbRouteDecision(
            ab_group="challenger",
            model_version=challenger_version,
            model_path_key="challenger",
        )
    return AbRouteDecision(
        ab_group="champion",
        model_version=champion_version,
        model_path_key="champion",
    )


def unit_id_from_record(record: dict[str, Any], index: int) -> str:
    for key in ("request_id", "ID", "id", "client_id"):
        if key in record and record[key] is not None:
            return str(record[key])
    return f"row-{index}"
