# APP_DEPLOYMENT_PREFLIGHT — Block 11.9.1

**Scope:** prepare real ML app deploy to existing cloud-experiment cluster via **private GHCR**.
**Publish / apply / kubectl apply of app:** **NOT_EXECUTED** this block (later closed as `ABORT_CLOUD_APP` — [`BLOCK11_ABORT_AND_CLEANUP.md`](BLOCK11_ABORT_AND_CLEANUP.md)).

## Artifacts (local)

| Artifact | Present | SHA256 vs Block10 baseline |
|----------|---------|----------------------------|
| `models/credit_scoring_nn.onnx` (FP32) | YES | MATCH |
| `models/preprocessor.joblib` | YES | MATCH |
| `models/credit_scoring_nn.pt` | YES | MATCH |
| `models/credit_scoring_nn.quant.onnx` | YES | MATCH (not cloud champion) |
| `models/model_registry.json` | YES | MATCH |
| `dvc.lock` | YES | MATCH |

Do **not** publish raw model files to a public registry. Use private GHCR images built from `docker/Dockerfile.models` (copies ONNX FP32 + preprocessor only).

## Dockerfiles

| File | Role | Cloud notes |
|------|------|-------------|
| `docker/Dockerfile.api` | FastAPI + ORT | Multi-stage CPU |
| `docker/Dockerfile.models` | ONNX+preprocessor artifacts image | Private only |
| `docker/Dockerfile.frontend` | nginx UI | |
| `docker/Dockerfile.dvcdata` | DVC helper | Not required for serving path |

## Kubernetes

| Overlay | Use for experiment |
|---------|--------------------|
| `k8s/overlays/staging` | Preferred namespace `credit-scoring-staging`; modest resources |
| `k8s/overlays/production` | Higher resources + HPA min=2 — tighten HPA max for single node |
| NetworkPolicy base | Ingress-only allow frontend/API; Calico present in cluster |

## GHCR checklist (next approved stage)

1. Build locally with real ONNX/preprocessor (verify SHA256 before build).
2. Tag digest-pinned images under private GHCR:
   `ghcr.io/serg2311-prog/credit-scoring-api|models|frontend` (repo PRIVATE).
3. Create `imagePullSecret` in target namespace (token never committed; requires `read:packages`/`write:packages` — currently **missing** on operator CLI token).
4. `kubectl apply` via dedicated `cloud-experiment` overlay with image digests patched (not production/staging unless needed).
5. Verify `/health/live`, `/health/ready`, real `/predict` (CLOUD_APP).
6. Optional: Prometheus/Grafana in-cluster **after** API Ready; HPA pod-only (no node scale).

## Blockers before app deploy

1. Complete **state migration** so future TF applies cannot wipe SG rules again.
2. Mitigate intermittent API TLS timeouts (stable admin network / retry).
3. Private GHCR packages + pull secret ready.
4. Explicit operator approval to publish images and apply manifests.

## Explicit non-goals now

- No `docker push`
- No synthetic CI model substitution
- No production registry / model retrain
