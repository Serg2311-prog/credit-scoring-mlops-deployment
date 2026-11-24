# Stage 3 Completion Report — Docker / K8s / Frontend / DVC

**Date:** 2026-11-24  
**Scope:** Close-out of Block 1–3 against original ТЗ (этап 3).  
**Commit/push:** not performed in this pass.

## Status legend (this report)

| Tag | Meaning |
| --- | --- |
| IMPLEMENTED | Code/manifests present |
| VERIFIED_LOCAL | Executed successfully on this machine |
| VERIFIED_CI | Proven in GitHub Actions (historical / prior commits) |
| PARTIAL | Implemented but not fully enforced/proven |
| UNVERIFIED | Not executed here |

## Results by requirement

| Item | Status | Evidence |
| --- | --- | --- |
| Multi-stage API image | VERIFIED_LOCAL | `docker build -f docker/Dockerfile.api` |
| Frontend image (separate) | VERIFIED_LOCAL | `Dockerfile.frontend`; compose UI `:8081` healthy |
| Frontend → API scoring | VERIFIED_LOCAL | `/api/predict` via compose + Ingress → `proba=0.830205` |
| Ingress resource | IMPLEMENTED + VERIFIED_LOCAL | Applied; E2E via **ingress-nginx controller** port-forward `:18080` (not frontend SVC) |
| Ingress host `:8080` on old kind | PARTIAL | Cluster predates `extraPortMappings`; recreate kind required |
| Invalid payload via Ingress | VERIFIED_LOCAL | HTTP **422** |
| NetworkPolicy manifests | IMPLEMENTED + VERIFIED_LOCAL | Applied; selectors/ports checked by script |
| NetworkPolicy traffic deny/allow | PARTIAL / UNVERIFIED | CNI=**kindnet** (no enforcement). Scenario documented for Calico/Cilium |
| DVC pipeline | VERIFIED_LOCAL | `dvc repro` / cache skip / `dvc push` / pull restore; `validate_ml_ready` smoke train |
| DVC-in-Docker | VERIFIED_LOCAL | `Dockerfile.dvcdata` repro→push→pull; busybox data-only final image |
| DVC not bloating API runtime | VERIFIED_LOCAL | DVC removed from `Dockerfile.api` |
| Production models untouched | VERIFIED_LOCAL | `git diff -- models/model_registry.json` empty; smoke metrics `writes_production_models=false` |
| Compose API+frontend | VERIFIED_LOCAL | ready + UI 200 |
| Kustomize render | VERIFIED_LOCAL | 10 resources |
| kubeconform | VERIFIED_LOCAL | 10/10 valid (k8s 1.33.0) |
| Full pytest | VERIFIED_LOCAL | **151 passed, 1 skipped** |
| black / flake8 | VERIFIED_LOCAL | PASS on `src tests scripts/dvc` |
| Trivy frontend gate in CI YAML | IMPLEMENTED | Workflow updated; **VERIFIED_CI not claimed** until push |
| Secrets in images | VERIFIED_LOCAL | No secrets copied; frontend `USER nginx`, `runAsNonRoot` |

## Ingress E2E (controller port-forward)

Method: `kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 18080:80`

| Check | Result |
| --- | --- |
| `GET /` | 200, contains «Credit Scoring» |
| `GET /health/ready` | ready / onnx |
| `GET /api/health/ready` | ready (frontend proxy) |
| `POST /api/predict` | success, proba=0.830205 |
| `POST /api/predict` invalid | 422 |

## DVC notes

- Tracks **synthetic** demo data under `data/dvc_tracked/` (not UCI raw CSV).
- Stages: `generate_demo` → `prepare_demo` → `validate_ml_ready`.
- Local remote `.dvc_remote/` gitignored.
- Changing outs shows `dvc status` dirty; unchanged `dvc repro` reports up-to-date (cache).
- Filename `Dockerfile.dvc` **cannot** be used — DVC treats `*.dvc` as metadata; use `Dockerfile.dvcdata`.

## NetworkPolicy notes

Allowed (by design):

- ingress-nginx → frontend:8080
- ingress-nginx → api:8000
- frontend → api:8000
- kube-system → probes
- optional `monitoring/prometheus` → api:8000 (for future in-cluster Prometheus)

Compose Prometheus scrapes Docker network `api:8000` and is **outside** these K8s policies.

## Remaining limits

1. kindnet does not enforce NetworkPolicy → deny probes UNVERIFIED on this cluster.
2. Host Ingress `:8080` needs kind cluster recreate with updated `k8s/kind/cluster.yaml`.
3. New CI Docker jobs (frontend/DVC Trivy) not yet run on GitHub → VERIFIED_CI pending push.
4. Documentation sync for stages 4–7 deferred to later blocks.

## Score forecast (Stage 3 / 8, original ТЗ)

**7.5–8.0 / 8** after this close-out (frontend, Ingress E2E, DVC pipeline+Docker verified).  
Deduction risk only if mentor requires live NetworkPolicy enforcement or kind host-port Ingress without recreate.
