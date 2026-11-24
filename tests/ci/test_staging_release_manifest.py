"""Tests for staging → production provenance manifest."""

from __future__ import annotations

import pytest

from scripts.ci.staging_release_manifest import (
    SCHEMA,
    build_manifest,
    verify_manifest_for_production,
)

API = "ghcr.io/acme/credit-scoring-api@sha256:" + ("a" * 64)
MODELS = "ghcr.io/acme/credit-scoring-models@sha256:" + ("b" * 64)
FRONTEND = "ghcr.io/acme/credit-scoring-frontend@sha256:" + ("c" * 64)
SHA = "deadbeefcafebabe0123456789abcdef01234567"


def _deploy_manifest(**overrides):
    base = build_manifest(
        git_sha=SHA,
        api_ref=API,
        models_ref=MODELS,
        frontend_ref=FRONTEND,
        staging_workflow_run_id=12345,
        mode="deploy",
        smoke={"ok": True, "base_url": "https://stg.example", "host": "stg"},
    )
    base.update(overrides)
    return base


def test_build_deploy_manifest_requires_smoke():
    with pytest.raises(ValueError, match="smoke"):
        build_manifest(
            git_sha=SHA,
            api_ref=API,
            models_ref=MODELS,
            frontend_ref=FRONTEND,
            staging_workflow_run_id=1,
            mode="deploy",
            smoke={"ok": False},
        )


def test_publish_manifest_not_production_eligible():
    m = build_manifest(
        git_sha=SHA,
        api_ref=API,
        models_ref=MODELS,
        frontend_ref=FRONTEND,
        staging_workflow_run_id=1,
        mode="publish",
    )
    assert m["status"] == "published_not_deployed"
    assert m["schema"] == SCHEMA
    result = verify_manifest_for_production(m, expect_git_sha=SHA, expect_run_id="1")
    assert result["ok"] is False
    assert any("staging_verified" in e for e in result["errors"])


def test_verify_happy_path():
    m = _deploy_manifest()
    result = verify_manifest_for_production(
        m, expect_git_sha=SHA, expect_run_id="12345"
    )
    assert result["ok"] is True
    assert result["images"]["api"] == API


def test_reject_other_sha():
    m = _deploy_manifest()
    result = verify_manifest_for_production(
        m, expect_git_sha="0" * 40, expect_run_id="12345"
    )
    assert result["ok"] is False
    assert any("git_sha" in e for e in result["errors"])


def test_reject_digest_substitution():
    m = _deploy_manifest()
    other = "ghcr.io/acme/credit-scoring-api@sha256:" + ("d" * 64)
    result = verify_manifest_for_production(
        m,
        expect_git_sha=SHA,
        expect_run_id="12345",
        allow_api_ref=other,
    )
    assert result["ok"] is False
    assert any("substitution" in e for e in result["errors"])


def test_reject_smoke_failed():
    m = _deploy_manifest()
    m["smoke"] = {"ok": False, "failed": "ready"}
    # status still staging_verified would be inconsistent; force both
    m["status"] = "staging_verified"
    result = verify_manifest_for_production(
        m, expect_git_sha=SHA, expect_run_id="12345"
    )
    assert result["ok"] is False
    assert any("smoke" in e for e in result["errors"])


def test_reject_missing_or_wrong_status():
    m = _deploy_manifest()
    m["status"] = "published_not_deployed"
    result = verify_manifest_for_production(
        m, expect_git_sha=SHA, expect_run_id="12345"
    )
    assert result["ok"] is False


def test_reject_latest_tag():
    with pytest.raises(ValueError, match="latest"):
        build_manifest(
            git_sha=SHA,
            api_ref="ghcr.io/acme/credit-scoring-api:latest",
            models_ref=MODELS,
            frontend_ref=FRONTEND,
            staging_workflow_run_id=1,
            mode="publish",
        )


def test_reject_wrong_run_id():
    m = _deploy_manifest()
    result = verify_manifest_for_production(
        m, expect_git_sha=SHA, expect_run_id="99999"
    )
    assert result["ok"] is False
    assert any("run_id" in e for e in result["errors"])
