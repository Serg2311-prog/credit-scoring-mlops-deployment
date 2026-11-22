# Stage 3A Validation Report — Kubernetes Local (kind)

**Date:** 2026-11-22  
**Scope:** kind + Kustomize + ONNX API Deployment only  
**Not done:** Stage 3B, Ingress, Terraform, cloud, Prometheus Operator, git commit/push

## Tool versions

| Tool | Version |
| --- | --- |
| Docker | 29.3.1 |
| kind | v0.29.0 (portable `tools/kind.exe`) |
| kubectl client | v1.34.1 |
| Kubernetes (kind node) | v1.33.1 |
| Node image | kindest/node:v1.33.1 |

## Model delivery

Trusted local image `credit-scoring-models:stage3a` (`docker/Dockerfile.models`)  
→ `kind load docker-image`  
→ initContainer `copy-models` → `emptyDir`  
→ API mount `/app/models` read-only  

No Windows hostPath. No ConfigMap/Secret binaries.

## `kubectl get pods -o wide` (after rollback)

```text
NAME                                 READY   STATUS    RESTARTS   AGE   IP           NODE
credit-scoring-api-6dd77467d-6bqhq   1/1     Running   0          82s   10.244.0.7   credit-scoring-control-plane
```

## Readiness / liveness

| Check | Result |
| --- | --- |
| `/health/live` | **200** `{"status":"ok"}` |
| `/health/ready` | **200** ready, model+preprocessor loaded, backend=onnx |
| Probes on Pod | Ready=True, ContainersReady=True |

## Real inference (via port-forward)

Sample client (same as stage 2):

```json
{
  "probability_default": 0.830205,
  "prediction": 1,
  "model_version": "mlp-onnx-fp32-v1"
}
```

Batch size 2 returned identical ordered results. `/metrics` returned Prometheus text (~6686 bytes).

## Rollout / rollback

```text
REVISION 1 → patch annotation → REVISION 2 → rollout undo → REVISION 3
OK: rollout + rollback completed
```

Strategy: `maxSurge: 0`, `maxUnavailable: 1` (brief downtime; not zero-downtime).

## CPU / RAM

| Scope | Value |
| --- | --- |
| API requests | cpu 100m / memory 256Mi |
| API limits | cpu 1 / memory 512Mi |
| QoS | Burstable |
| API container (crictl) | **~146 MB** |
| kind node (docker stats) | ~885 MiB / 7.5 GiB |
| metrics-server | not installed → `kubectl top` unavailable (expected) |

## Quality gates

```text
pytest  -> 67 passed
flake8  -> 0
black   -> 0
kubectl kustomize k8s/overlays/local -> OK
```

## Acceptance criteria

| # | Criterion | Result |
| --- | ---: | --- |
| 1 | Manifests valid | **PASS** |
| 2 | Kustomize local overlay | **PASS** |
| 3 | kind cluster created | **PASS** |
| 4 | Images loaded into kind | **PASS** |
| 5 | Model+preprocessor in Pod | **PASS** |
| 6 | Deployment Available | **PASS** |
| 7 | Pod Ready | **PASS** |
| 8 | Service routes to API | **PASS** |
| 9 | `/predict` + `/predict/batch` | **PASS** |
| 10 | `/metrics` | **PASS** |
| 11 | Rollout + rollback | **PASS** |
| 12 | Resource limits applied | **PASS** |
| 13 | pytest / flake8 / black | **PASS** |
| 14 | Docs with real results | **PASS** |

## Known issues / notes

1. `kubectl top` SKIPPED — metrics-server not installed (by design for 3A).
2. Portable kind under `tools/` (gitignored binary); install command documented.
3. Rolling update with `maxSurge: 0` causes short unavailability on 1 replica.
4. Cluster left running; destroy only via `.\scripts\k8s_destroy.ps1 -Confirm credit-scoring`.

## Stage 3A readiness

**Stage 3A complete and verified on local kind.**  
Do not start Stage 3B without approval.
