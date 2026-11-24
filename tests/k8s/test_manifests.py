"""Static validation of Stage 3A Kubernetes manifests (no cluster required)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "k8s" / "overlays" / "local"
BASE = ROOT / "k8s" / "base"
SCRIPTS = ROOT / "scripts"


def _load_kustomize() -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(OVERLAY)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"kubectl kustomize unavailable: {result.stderr.strip()}")
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    assert docs, "kustomize produced no documents"
    return docs


def _by_kind(docs: list[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def test_required_files_exist():
    required = [
        ROOT / "k8s" / "kind" / "cluster.yaml",
        BASE / "namespace.yaml",
        BASE / "configmap.yaml",
        BASE / "deployment.yaml",
        BASE / "service.yaml",
        BASE / "frontend-deployment.yaml",
        BASE / "frontend-service.yaml",
        BASE / "ingress.yaml",
        BASE / "networkpolicy.yaml",
        BASE / "kustomization.yaml",
        BASE / "secret.example.yaml",
        OVERLAY / "kustomization.yaml",
        OVERLAY / "patch-resources.yaml",
        ROOT / "docker" / "Dockerfile.models",
        ROOT / "docker" / "Dockerfile.frontend",
        ROOT / "docker" / "Dockerfile.dvcdata",
        ROOT / "frontend" / "index.html",
        ROOT / "frontend" / "app.js",
        ROOT / "dvc.yaml",
        ROOT / "dvc.lock",
    ]
    for path in required:
        assert path.is_file(), f"missing {path}"


def test_automation_scripts_exist():
    names = [
        "k8s_common.ps1",
        "k8s_create.ps1",
        "k8s_build_load.ps1",
        "k8s_deploy.ps1",
        "k8s_smoke.ps1",
        "k8s_rollback.ps1",
        "k8s_destroy.ps1",
    ]
    for name in names:
        assert (SCRIPTS / name).is_file()


def test_secret_example_not_in_kustomize_resources():
    kust = yaml.safe_load((BASE / "kustomization.yaml").read_text(encoding="utf-8"))
    resources = kust.get("resources") or []
    assert "secret.example.yaml" not in resources
    assert not any("secret" in str(r).lower() for r in resources)


def test_no_real_secret_manifests_in_git():
    secrets = list((ROOT / "k8s").rglob("*.yaml"))
    for path in secrets:
        if path.name.endswith(".example.yaml"):
            continue
        text = path.read_text(encoding="utf-8")
        if "kind: Secret" in text:
            pytest.fail(f"Real Secret manifest must not be committed: {path}")


def test_kustomize_renders_expected_resources():
    docs = _load_kustomize()
    kinds = {d["kind"] for d in docs}
    assert {
        "Namespace",
        "ConfigMap",
        "Deployment",
        "Service",
        "Ingress",
        "NetworkPolicy",
    } <= kinds
    assert "Secret" not in kinds
    deployments = {d["metadata"]["name"] for d in _by_kind(docs, "Deployment")}
    assert {
        "credit-scoring-api",
        "credit-scoring-frontend",
    } <= deployments
    policies = {d["metadata"]["name"] for d in _by_kind(docs, "NetworkPolicy")}
    assert {
        "default-deny-ingress",
        "allow-frontend",
        "allow-api",
    } <= policies
    allow_api = next(
        d
        for d in _by_kind(docs, "NetworkPolicy")
        if d["metadata"]["name"] == "allow-api"
    )
    api_from = allow_api["spec"]["ingress"][0].get("from") or []
    assert any(
        (f.get("podSelector") or {})
        .get("matchLabels", {})
        .get("app.kubernetes.io/name")
        == "credit-scoring-frontend"
        for f in api_from
    )
    assert any(
        (f.get("namespaceSelector") or {})
        .get("matchLabels", {})
        .get("kubernetes.io/metadata.name")
        == "ingress-nginx"
        for f in api_from
    )
    ingress = _by_kind(docs, "Ingress")[0]
    assert ingress["spec"]["ingressClassName"] == "nginx"


def test_deployment_security_and_probes():
    docs = _load_kustomize()
    dep = _by_kind(docs, "Deployment")[0]
    assert dep["metadata"]["name"] == "credit-scoring-api"
    assert dep["spec"]["replicas"] == 1

    strategy = dep["spec"]["strategy"]["rollingUpdate"]
    assert strategy["maxSurge"] == 0
    assert strategy["maxUnavailable"] == 1

    pod = dep["spec"]["template"]["spec"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == 10001
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert "hostNetwork" not in pod
    assert "hostPID" not in pod

    init = pod["initContainers"][0]
    assert init["name"] == "copy-models"
    assert init["imagePullPolicy"] == "IfNotPresent"
    assert "credit-scoring-models" in init["image"]
    assert init["securityContext"]["allowPrivilegeEscalation"] is False
    assert init["securityContext"]["capabilities"]["drop"] == ["ALL"]

    ctr = pod["containers"][0]
    assert ctr["name"] == "api"
    assert ctr["imagePullPolicy"] == "IfNotPresent"
    assert "credit-scoring-api" in ctr["image"]
    assert ctr["securityContext"]["allowPrivilegeEscalation"] is False
    assert ctr["securityContext"]["readOnlyRootFilesystem"] is True
    assert ctr["securityContext"]["capabilities"]["drop"] == ["ALL"]

    assert ctr["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert ctr["readinessProbe"]["httpGet"]["path"] == "/health/ready"
    assert ctr["startupProbe"]["httpGet"]["path"] == "/health/live"

    res = ctr["resources"]
    assert res["requests"]["cpu"] == "100m"
    assert res["requests"]["memory"] == "256Mi"
    assert res["limits"]["cpu"] == "1"
    assert res["limits"]["memory"] == "512Mi"

    mounts = {m["name"]: m for m in ctr["volumeMounts"]}
    assert mounts["model-data"]["mountPath"] == "/app/models"
    assert mounts["model-data"].get("readOnly") is True
    assert "tmp" in mounts

    vol_names = {v["name"] for v in pod["volumes"]}
    assert {"model-data", "tmp"} <= vol_names
    assert all("hostPath" not in v for v in pod["volumes"])


def test_service_selector_matches_deployment_labels():
    docs = _load_kustomize()
    dep = _by_kind(docs, "Deployment")[0]
    svc = _by_kind(docs, "Service")[0]
    assert svc["spec"]["type"] == "ClusterIP"
    assert svc["spec"]["selector"] == dep["spec"]["selector"]["matchLabels"]
    assert svc["spec"]["ports"][0]["port"] == 8000
    annotations = svc["metadata"].get("annotations") or {}
    assert annotations.get("prometheus.io/scrape") == "true"
    assert annotations.get("prometheus.io/path") == "/metrics"


def test_configmap_matches_stage2_env():
    docs = _load_kustomize()
    cm = _by_kind(docs, "ConfigMap")[0]
    data = cm["data"]
    assert data["MODEL_BACKEND"] == "onnx"
    assert data["MODEL_VERSION"] == "mlp-onnx-fp32-v1"
    assert data["PREDICTION_THRESHOLD"] == "0.5"
    assert data["MAX_BATCH_SIZE"] == "256"
    assert data["MODEL_PATH"] == "/app/models/credit_scoring_nn.onnx"
    assert data["PREPROCESSOR_PATH"] == "/app/models/preprocessor.joblib"
    assert data["ORT_INTRA_OP_THREADS"] == "2"
    assert data["EXPECTED_INPUT_DIM"] == "47"


def test_destroy_script_requires_confirmation():
    text = (SCRIPTS / "k8s_destroy.ps1").read_text(encoding="utf-8")
    assert "-Confirm" in text
    assert "delete cluster" in text.lower()


def test_kind_cluster_is_single_control_plane():
    cluster = yaml.safe_load(
        (ROOT / "k8s" / "kind" / "cluster.yaml").read_text(encoding="utf-8")
    )
    assert cluster["kind"] == "Cluster"
    assert cluster["name"] == "credit-scoring"
    assert len(cluster["nodes"]) == 1
    assert cluster["nodes"][0]["role"] == "control-plane"
