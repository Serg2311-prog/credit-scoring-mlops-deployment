"""Static checks for Stage 4 GitHub Actions workflows and CI scripts."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
SCRIPTS = ROOT / "scripts" / "ci"


REQUIRED_WORKFLOWS = [
    "ci-python.yml",
    "ci-infrastructure.yml",
    "ci-docker.yml",
    "ci-kubernetes.yml",
    "release-candidate.yml",
    "cd-staging.yml",
]


def _text(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


def test_required_workflow_files_exist():
    for name in REQUIRED_WORKFLOWS:
        assert (WF / name).is_file(), name
        # Ensure YAML parses (PyYAML maps key "on" to True — still a dict).
        loaded = yaml.safe_load(_text(name))
        assert isinstance(loaded, dict)


def test_ci_scripts_exist():
    for name in (
        "check.ps1",
        "build_images.ps1",
        "smoke.ps1",
        "generate_synthetic_artifacts.py",
        "verify_artifacts.py",
    ):
        assert (SCRIPTS / name).is_file(), name


def test_python_ci_has_quality_gates():
    text = _text("ci-python.yml")
    assert "pull_request:" in text
    assert "pytest" in text
    assert "flake8" in text
    assert "black" in text
    assert "generate_synthetic_artifacts" in text
    assert "ubuntu-latest" in text


def test_infra_ci_validates_terraform_and_kustomize():
    text = (WF / "ci-infrastructure.yml").read_text(encoding="utf-8")
    assert "terraform fmt" in text
    assert "validate" in text
    assert "kustomize" in text
    assert "terraform apply" not in text


def test_docker_ci_builds_and_scans():
    text = (WF / "ci-docker.yml").read_text(encoding="utf-8")
    assert "Dockerfile.api" in text
    assert "Dockerfile.models" in text
    assert "trivy" in text.lower()
    assert "yandex" not in text.lower() or "push" not in text.lower()


def test_cd_staging_is_manual_and_dry_run():
    text = _text("cd-staging.yml")
    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "deploy-staging-dry-run" in text
    assert "terraform apply" in text  # listed as blocked
    assert "SKIPPED_NO_CLOUD_CREDENTIALS" in text
    assert "environment: staging" in text


def test_release_candidate_does_not_create_github_release():
    text = (WF / "release-candidate.yml").read_text(encoding="utf-8")
    assert "softprops/action-gh-release" not in text
    assert "Not a GitHub Release" in text
    assert "workflow_dispatch" in text


def test_no_cloud_credentials_in_workflows():
    for path in WF.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "YC_TOKEN" not in text
        assert "AWS_SECRET_ACCESS_KEY" not in text
        assert "private_key" not in text


def test_kind_smoke_is_optional():
    text = (WF / "ci-kubernetes.yml").read_text(encoding="utf-8")
    assert "run_kind_smoke" in text
    assert "kind create cluster" in text
