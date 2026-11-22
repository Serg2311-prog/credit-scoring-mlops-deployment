"""Static checks for Stage 3B Terraform layout (no cloud calls)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TF_ROOT = ROOT / "infra" / "terraform"
MODULES = TF_ROOT / "modules"
ENVS = TF_ROOT / "environments"


REQUIRED_MODULES = [
    "network",
    "iam",
    "kubernetes",
    "registry",
    "storage",
    "monitoring",
]

REQUIRED_MODULE_FILES = ["main.tf", "variables.tf", "outputs.tf", "versions.tf"]

REQUIRED_ENV_FILES = [
    "main.tf",
    "variables.tf",
    "outputs.tf",
    "providers.tf",
    "versions.tf",
    "terraform.tfvars.example",
    "backend.tf.example",
]


def _read_all_tf() -> str:
    parts: list[str] = []
    for path in TF_ROOT.rglob("*"):
        if path.suffix in {".tf", ".example", ".md"} and path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_required_modules_and_files_exist():
    for name in REQUIRED_MODULES:
        mod = MODULES / name
        assert mod.is_dir(), f"missing module {name}"
        for fname in REQUIRED_MODULE_FILES:
            assert (mod / fname).is_file(), f"missing {mod / fname}"


def test_environments_isolated():
    for env in ("staging", "production"):
        env_dir = ENVS / env
        assert env_dir.is_dir()
        for fname in REQUIRED_ENV_FILES:
            assert (env_dir / fname).is_file(), f"missing {env_dir / fname}"


def test_staging_and_production_use_distinct_cidrs():
    stg = (ENVS / "staging" / "main.tf").read_text(encoding="utf-8")
    prod = (ENVS / "production" / "main.tf").read_text(encoding="utf-8")
    stg_cidrs = re.findall(r'cidr\s*=\s*"([^"]+)"', stg)
    prod_cidrs = re.findall(r'cidr\s*=\s*"([^"]+)"', prod)
    assert stg_cidrs == ["10.20.0.0/24"]
    assert prod_cidrs == ["10.30.0.0/24"]
    assert set(stg_cidrs).isdisjoint(set(prod_cidrs))


def test_no_hardcoded_credentials():
    text = _read_all_tf()
    forbidden = [
        r"YC_TOKEN\s*=\s*\"[^\"]{20,}\"",
        r"private_key\s*=\s*\"-----BEGIN",
        r"secret_key\s*=\s*\"[A-Za-z0-9/+=]{20,}\"",
        r"oauth_token\s*=\s*\"y0_",
        r"AQVN[A-Za-z0-9_-]{20,}",
    ]
    for pattern in forbidden:
        assert re.search(pattern, text) is None, f"possible secret matched {pattern}"


def test_no_open_ssh_ingress():
    network = (MODULES / "network" / "main.tf").read_text(encoding="utf-8")
    # No SSH port 22 ingress from world.
    assert "port           = 22" not in network
    assert "port = 22" not in network
    assert "port               = 22" not in network


def test_api_cidr_rejects_world_open_default():
    variables = (MODULES / "network" / "variables.tf").read_text(encoding="utf-8")
    assert 'c != "0.0.0.0/0"' in variables
    assert "k8s_api_allowed_cidrs" in variables


def test_object_storage_is_private():
    storage = (MODULES / "storage" / "main.tf").read_text(encoding="utf-8")
    assert "anonymous_access_flags" in storage
    assert "read        = false" in storage
    assert "list        = false" in storage
    assert "config_read = false" in storage
    # Do not use world-readable ACL shortcuts.
    assert 'acl = "public-read"' not in storage
    assert 'acl       = "public-read"' not in storage


def test_iam_avoids_broad_admin_roles():
    iam = (MODULES / "iam" / "main.tf").read_text(encoding="utf-8")
    assert '"editor"' not in iam
    assert '"admin"' not in iam
    assert "k8s.clusters.agent" in iam
    assert "storage.viewer" in iam
    assert "container-registry.images.pusher" in iam


def test_no_apply_in_scripts_or_docs_as_default_command():
    readme = (TF_ROOT / "README.md").read_text(encoding="utf-8")
    assert "No `terraform apply`" in readme or "no `terraform apply`" in readme.lower()
    assert "terraform apply" in readme  # mentioned as forbidden


def test_provider_version_pinned():
    for env in ("staging", "production"):
        versions = (ENVS / env / "versions.tf").read_text(encoding="utf-8")
        assert "yandex-cloud/yandex" in versions
        assert "0.250" in versions


def test_k8s_cpu_only_no_gpu():
    k8s = (MODULES / "kubernetes" / "main.tf").read_text(encoding="utf-8")
    assert "gpus" not in k8s.lower() or "gpus =" not in k8s
    assert "standard-v3" in (ENVS / "staging" / "main.tf").read_text(encoding="utf-8")


def test_consistency_with_stage3a_service_port_and_paths():
    # Cloud deploy will reuse stage-3A API contract; ensure docs/module notes align.
    mon = (MODULES / "monitoring" / "outputs.tf").read_text(encoding="utf-8")
    assert "/metrics" in mon
    k8s_svc = (ROOT / "k8s" / "base" / "service.yaml").read_text(encoding="utf-8")
    assert "port: 8000" in k8s_svc
    assert "prometheus.io/scrape" in k8s_svc


def test_gitignore_covers_tfstate_and_tfvars():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.tfstate" in gi
    assert "*.tfvars" in gi
    assert "!*.tfvars.example" in gi or "!.tfvars.example" in gi
    assert ".terraform/" in gi or "**/.terraform/" in gi
