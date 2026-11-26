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
| DVC-in-Docker | VERIFIED_LOCAL | `Dockerfile.dvcdata` build-stage repro→push→pull; runtime Alpine `nobody` + CMD lists `/data/dvc_tracked`; host `dvc repro` cache-skip + push/pull OK |
| DVC not bloating API runtime | VERIFIED_LOCAL | DVC removed from `Dockerfile.api` |
| Production models untouched | VERIFIED_LOCAL | `git diff -- models/` empty after hotfix; smoke metrics `writes_production_models=false` |
| Compose API+frontend | VERIFIED_LOCAL | ready + UI 200 |
| Kustomize render | VERIFIED_LOCAL | 10 resources |
| kubeconform | VERIFIED_LOCAL | 10/10 valid |
| Full pytest | VERIFIED_LOCAL | **151 passed, 1 skipped** |
| black / flake8 | VERIFIED_LOCAL | CI scope `src tests scripts/ci airflow_home/dags` PASS (black 26.10.1 / flake8 7.5.0). Prior local FAIL was from linting `.` outside CI paths (`artifacts/ci/*` generated; `monitoring/` not in CI). |
| Trivy frontend / DVC gates | VERIFIED_LOCAL | Local Trivy v0.70.0 Total **0** (CRITICAL/HIGH fixed); **VERIFIED_CI not claimed** until GHA |
| Secrets in images | VERIFIED_LOCAL | Trivy secret scanner enabled; frontend `USER nginx`, `runAsNonRoot` |

## HOTFIX — Trivy frontend / CI Docker (2026-11-24)

Root cause (GHA run `45350959039`): frontend base `nginx:1.27-alpine` (Alpine **3.21.3**) shipped outdated OS packages → Trivy Total **70** (HIGH 67 / CRITICAL 3), including CVE-2026-111497 (brotli-libs) and CVE-2026-31789 (libcrypto3/libssl3). DVC Trivy step was **SKIPPED** after frontend failure (sequential steps).

| Item | Before | After |
| --- | --- | --- |
| Frontend base | `nginx:1.27-alpine` (nginx 1.27.5 / Alpine 3.21.3) | `nginx:1.30.8-alpine@sha256:6437a63b5c529f0e06162b3f593c0154cff6fa2ea0f94fd7c27928cb399e022d` + same-branch `apk upgrade` (Alpine **3.24.4**, nginx **1.30.8**) |
| Key packages | brotli/openssl outdated on 3.21.3 | brotli-libs **1.2.1-r0**, libcrypto3/libssl3 **3.5.9-r1**, zlib **1.4-r0** |
| Trivy frontend (CRITICAL,HIGH, ignore-unfixed) | Total **70** (H67/C3) | Total **0** (exit 0) |
| Trivy frontend full (incl. unfixed) | n/a | Total **0** |
| DVC final base | `busybox:1.36` (OS not detectable by Trivy) | `alpine:3.21@sha256:bc21487101ae47172509130ee1092cc273a831968d64b617776d1f69c81e42ab` + `apk upgrade` (Alpine **3.21.10**) |
| Trivy DVC gate | SKIPPED in CI | Total **0** (exit 0), OS detected |
| CI workflow | Sequential scans; DVC skipped on frontend fail | Independent scans (`if: always` + `continue-on-error`) + mandatory final **Security gate** |

Preserved: non-root `USER nginx`, K8s `runAsNonRoot` / `readOnlyRootFilesystem` / `drop ALL`, reverse-proxy, healthcheck, compose + Ingress integration.

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
- `dvc.lock` trailing whitespace stripped on cmd wrap lines only; YAML-folded cmd strings unchanged.

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
3. Hotfix CI Docker (independent Trivy + security gate) not yet run on GitHub → **VERIFIED_CI pending** push/Actions.
4. Documentation sync for stages 4–7 deferred to later blocks.
