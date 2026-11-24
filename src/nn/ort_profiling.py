"""Structured ONNX Runtime profiling helpers (Node events / provider checks)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_ort_profile(path: Path | str) -> list[dict[str, Any]]:
    """Load ORT chrome-style profile JSON (list of events)."""
    raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("traceEvents", "events"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError(f"Unrecognized ORT profile schema: {path}")


def iter_node_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return events with cat == 'Node' (case-sensitive ORT convention)."""
    return [e for e in events if e.get("cat") == "Node"]


def analyze_ort_node_providers(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Count Node-event providers from args.provider (structured, not text search)."""
    nodes = iter_node_events(events)
    providers: dict[str, int] = {}
    missing_provider = 0
    for event in nodes:
        args = event.get("args") or {}
        provider = args.get("provider")
        if not provider:
            missing_provider += 1
            continue
        providers[str(provider)] = providers.get(str(provider), 0) + 1
    cuda_nodes = providers.get("CUDAExecutionProvider", 0)
    cpu_nodes = providers.get("CPUExecutionProvider", 0)
    other_cpuish = sum(
        n for p, n in providers.items() if "CPU" in p and p != "CUDAExecutionProvider"
    )
    ok = (
        len(nodes) > 0
        and missing_provider == 0
        and cuda_nodes == len(nodes)
        and cpu_nodes == 0
        and other_cpuish == 0
    )
    return {
        "n_events_total": len(events),
        "n_node_events": len(nodes),
        "providers": providers,
        "cuda_node_events": cuda_nodes,
        "cpu_node_events": cpu_nodes,
        "missing_provider_on_node": missing_provider,
        "all_nodes_on_cuda": ok,
        "status": "PASS" if ok else "FAIL",
    }


def require_cuda_only_nodes(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Raise if profiling does not confirm CUDA-only Node placement."""
    analysis = analyze_ort_node_providers(events)
    if analysis["n_node_events"] == 0:
        raise RuntimeError(
            "ORT profiling has zero Node events — cannot claim VERIFIED_GPU"
        )
    if analysis["cpu_node_events"] > 0:
        raise RuntimeError(
            "ORT profiling contains CPU Node events — refusing VERIFIED_GPU"
        )
    if not analysis["all_nodes_on_cuda"]:
        raise RuntimeError(
            "ORT profiling Node providers are not exclusively CUDAExecutionProvider: "
            f"{analysis}"
        )
    return analysis
