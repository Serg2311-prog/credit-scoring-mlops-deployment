"""Static tests for Block 5 / 5.1 CI/CD orchestration and fail-closed gates."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"


def _text(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


def test_cicd_orchestrator_modes_and_auto_opt_in():
    text = _text("ci-cd.yml")
    assert "workflow_dispatch:" in text
    assert "workflow_run:" in text
    assert "CI Airflow DAG" in text
    assert "AUTO_STAGING_ENABLED" in text
    assert "pull_request:" not in text
    assert "mode" in text
    assert "validation" in text
    assert "publish" in text
    assert "deploy" in text
    assert "check_required_ci.py" in text
    assert "--incomplete-as-wait" in text
    assert "--expect-branch-tip main" in text
    assert "ghcr.io" in text
    assert "trivy image" in text
    assert "environment: staging" in text
    assert "STAGING_KUBECONFIG" in text
    assert "STAGING_SMOKE_BASE_URL" in text
    assert "FAIL-CLOSED" in text
    assert "smoke_http.py" in text
    assert "staging_release_manifest.py" in text
    assert "staging-release.json" in text
    assert "cancel-in-progress: true" in text
    assert "terraform apply" not in text.lower() or "never" in text.lower()
    # Deploy must not soft-succeed without secrets
    deploy_idx = text.index("Staging deploy (fail-closed)")
    deploy_chunk = text[deploy_idx:]
    assert (
        "Requires kubeconfig + smoke variables" in deploy_chunk
        or "FAIL-CLOSED" in deploy_chunk
    )
    assert "exit 1" in deploy_chunk
    # Smoke not gated on empty URL for deploy mode
    assert "Mandatory smoke tests" in text


def test_cicd_no_pr_and_main_auto_only():
    text = _text("ci-cd.yml")
    assert "pull_request:" not in text
    assert "workflow_run:" in text
    assert "branches: [main]" in text
    for required in (
        "CI Python",
        "CI Docker",
        "CI Infrastructure",
        "CI Kubernetes",
        "CI Airflow DAG",
    ):
        assert required in text


def test_cd_production_provenance_not_freeform_digests():
    text = _text("cd-production.yml")
    assert "environment: production" in text
    assert "promote-production" in text
    assert "staging_run_id" in text
    assert "staging_release_manifest.py" in text
    assert "fetch" in text
    assert "refs/heads/main" in text
    assert "pull_request:" not in text
    assert "check_required_ci.py" in text
    assert "PRODUCTION_KUBECONFIG" in text
    assert "FAIL-CLOSED" in text
    assert "Mandatory production smoke" in text
    assert "cancel-in-progress: false" in text
    assert "group: cd-production" in text
    assert "docker build" not in text
    assert "render_cd_images.py" in text
    # Free-form required digest inputs removed — provenance supplies digests
    assert "staging_run_id:" in text
    assert "claim_api_ref:" in text
    # workflow_dispatch inputs must not require free-form api_ref
    assert 'api_ref:\n        description: "ghcr.io' not in text
    assert "mode:" in text


def test_cd_staging_dry_run_still_gates_ci():
    text = _text("cd-staging.yml")
    assert "deploy-staging-dry-run" in text
    assert "check_required_ci.py" in text
    assert "environment: staging" in text
    assert "SKIPPED_NO_CLOUD_CREDENTIALS" in text
    assert "pull_request:" not in text


def test_overlays_staging_production_exist():
    for name in (
        "staging",
        "production",
        "cd-demo-staging",
        "cd-demo-production",
    ):
        path = ROOT / "k8s" / "overlays" / name / "kustomization.yaml"
        assert path.is_file(), name
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data.get("namespace")


def test_cd_scripts_exist():
    for name in (
        "check_required_ci.py",
        "smoke_http.py",
        "render_cd_images.py",
        "staging_release_manifest.py",
        "local_cd_verify.ps1",
    ):
        assert (ROOT / "scripts" / "ci" / name).is_file(), name


def test_check_required_defaults_five_workflows():
    text = (ROOT / "scripts" / "ci" / "check_required_ci.py").read_text(
        encoding="utf-8"
    )
    assert "CI Airflow DAG" in text
    assert "CI Python" in text
    assert "incomplete-as-wait" in text or "incomplete_as_wait" in text
    assert "expect-branch-tip" in text or "expect_branch_tip" in text


def test_workflows_forbid_embedding_cloud_tokens():
    for path in WF.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "YC_TOKEN" not in text
        assert "AWS_SECRET_ACCESS_KEY" not in text
        assert "BEGIN PRIVATE KEY" not in text


def test_actions_sha_pinned_in_new_workflows():
    for name in ("ci-cd.yml", "cd-production.yml", "cd-staging.yml"):
        text = _text(name)
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses:"):
                continue
            ref = stripped.split("uses:", 1)[1].strip().split()[0]
            assert "@" in ref
            sha = ref.split("@", 1)[1]
            assert len(sha) == 40, f"{name}: {ref}"


def test_fail_closed_modes_documented_in_orchestrator():
    text = _text("ci-cd.yml")
    assert "Validation-only render" in text
    assert "Publish-only release marker" in text or "publish-only" in text.lower()
    assert "Staging deploy (fail-closed)" in text
    # validation must not require kube secret
    val_idx = text.index("Validation-only render")
    val_chunk = text[val_idx : val_idx + 1200]
    assert "STAGING_KUBECONFIG" not in val_chunk
