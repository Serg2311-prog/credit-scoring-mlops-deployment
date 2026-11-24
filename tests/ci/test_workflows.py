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

TRIVY_SHA = "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25"


def _text(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


def _uses_lines(text: str) -> list[str]:
    refs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("uses:"):
            refs.append(stripped.split("uses:", 1)[1].strip())
    return refs


def test_required_workflow_files_exist():
    for name in REQUIRED_WORKFLOWS:
        assert (WF / name).is_file(), name
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
    text = _text("ci-infrastructure.yml")
    assert "terraform fmt" in text
    assert "validate" in text
    assert "kustomize" in text
    assert "kubeconform" in text
    assert "terraform apply" not in text
    assert "kubectl apply --dry-run" not in text
    assert "--validate=false" not in text


def test_docker_ci_builds_and_scans():
    text = _text("ci-docker.yml")
    assert "Dockerfile.api" in text
    assert "Dockerfile.models" in text
    assert "Dockerfile.frontend" in text
    assert "Dockerfile.dvcdata" in text
    assert "trivy" in text.lower()
    uses = _uses_lines(text)
    assert any(u.startswith(TRIVY_SHA) for u in uses)
    assert not any(u.startswith("aquasecurity/trivy-action@0.28.0") for u in uses)


def test_kubernetes_ci_uses_offline_kubeconform():
    text = _text("ci-kubernetes.yml")
    assert "kubeconform" in text
    assert 'KUBECONFORM_VERSION: "v0.6.7"' in text
    assert "kubectl apply --dry-run" not in text
    assert "--validate=false" not in text
    # Kind smoke applies rendered manifests (local overlay + synthetic ConfigMap patch).
    assert "k8s/overlays/local" in text
    assert "kubectl apply -f artifacts/ci/kustomize-kind-smoke.yaml" in text
    assert "kind create cluster" in text


def test_actions_are_sha_pinned():
    for path in WF.glob("*.yml"):
        for ref in _uses_lines(path.read_text(encoding="utf-8")):
            assert "@" in ref, f"unpinned action in {path.name}: {ref}"
            version = ref.split("@", 1)[1].split()[0]
            assert len(version) == 40 and all(
                c in "0123456789abcdef" for c in version
            ), f"action not pinned to full SHA in {path.name}: {ref}"


def test_cd_staging_is_manual_and_dry_run():
    text = _text("cd-staging.yml")
    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "deploy-staging-dry-run" in text
    assert "terraform apply" in text
    assert "SKIPPED_NO_CLOUD_CREDENTIALS" in text
    assert "environment: staging" in text


def test_release_candidate_does_not_create_github_release():
    text = _text("release-candidate.yml")
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
    text = _text("ci-kubernetes.yml")
    assert "run_kind_smoke" in text
    assert "kind create cluster" in text
    assert "free_runner_disk.sh" in text
    assert "disk_report.sh" in text
    assert "kind load docker-image" in text
    assert "/health/live" in text
    assert "/health/ready" in text
    assert "/predict" in text
    assert "/metrics" in text
    # Build before kind create to reduce peak disk pressure.
    assert text.index("Build API and models images") < text.index("Create kind cluster")
    assert "kind delete cluster" in text
    # Rollout failure diagnostics must run before cluster deletion.
    assert "k8s_diagnose.sh" in text
    assert "kind-smoke-diagnostics" in text
    assert "render_kind_manifests.py" in text
    assert text.index("Collect k8s diagnostics") < text.index("Delete kind cluster")
    assert text.index("Upload kind smoke diagnostics") < text.index(
        "Delete kind cluster"
    )


def test_ci_scripts_include_kind_helpers():
    assert (SCRIPTS / "k8s_diagnose.sh").is_file()
    assert (SCRIPTS / "render_kind_manifests.py").is_file()
    assert (SCRIPTS / "disk_report.sh").is_file()
    assert (SCRIPTS / "free_runner_disk.sh").is_file()
