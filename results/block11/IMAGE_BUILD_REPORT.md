# IMAGE_BUILD_REPORT — Block 11.10 (Trivy remediation)

**Owner GHCR:** `ghcr.io/serg2311-prog/...`
**Publish:** **NOT EXECUTED** (no push; packages scopes missing; API Trivy still FAIL).

> **Block 11.15 delivery note:** Experimental `Dockerfile.api` trixie remediation below is **historical only** and is **not** included in the final delivery. Delivery restores `docker/Dockerfile.api` to exact `main` (`python:3.12-slim-bookworm`). `Dockerfile.models` openssl remediation **is** included.

## Delivery / merge-prep Trivy (Block 11.15)

**Security gate (unchanged, matches CI):**
`trivy image --exit-code 1 --severity CRITICAL,HIGH --ignore-unfixed` (same as `.github/workflows/ci-docker.yml`). Gates were **not** weakened.

| Image | Tag | CRITICAL/HIGH (fixable) | Exit |
|-------|-----|--------------------------:|-----:|
| `credit-scoring-api` | `merge-prep-1115` | 0 / 0 | **0 PASS** |
| `credit-scoring-models` | `merge-prep-1115` | 0 / 0 | **0 PASS** |
| `credit-scoring-frontend` | `merge-prep-1115` | 0 / 0 | **0 PASS** |

Fresh local rebuilds were scanned for merge-prep; prior green CI runs are **not** used as proof.
**Historical vs delivery:** experiment API image used Debian **trixie** (53 HIGH / 0 CRITICAL, FixedVersion empty) — excluded from delivery. Final API image is **bookworm** from restored `Dockerfile.api` and passes the gate above.

## Before → After (CRITICAL/HIGH)

| Image | Before | After | Notes |
|-------|--------|-------|-------|
| models | FAIL — 2 HIGH (`libssl3`/`libcrypto3` 3.5.9-r0 → fix 3.5.9-r2) | **PASS — 0** | Forced `apk add --upgrade 'libssl3>=3.5.9-r2' 'libcrypto3>=3.5.9-r2'` |
| api | FAIL — 102 (2 CRITICAL + 100 HIGH), all debian bookworm, **FixedVersion empty** | FAIL — **53 HIGH, 0 CRITICAL**, all debian trixie, **FixedVersion empty** | Base moved `python:3.12-slim-bookworm` → `python:3.12.16-slim-trixie` + `apt-get upgrade` |
| frontend | PASS (unchanged) | PASS | Not rebuilt |

## CVE source classification

| Source | models before | api before | api after |
|--------|---------------|------------|-----------|
| Base OS / system packages | 2 (Alpine OpenSSL) | 102 (Debian) | 53 (Debian) |
| Python app deps (`python-pkg`) | 0 | 0 HIGH/CRIT in gate | 0 HIGH/CRIT in gate |

## Models — CVE table (before)

| CVE | Severity | Package | Installed | Fixed | Source |
|-----|----------|---------|-----------|-------|--------|
| CVE-2026-124709 | HIGH | libcrypto3 | 3.5.9-r0 | 3.5.9-r2 | Alpine base |
| CVE-2026-124709 | HIGH | libssl3 | 3.5.9-r0 | 3.5.9-r2 | Alpine base |

## API — representative CVE sample (after; all Fixed empty)

| CVE | Severity | Package | Installed | Fixed | Source |
|-----|----------|---------|-----------|-------|--------|
| CVE-2026-107494 | HIGH | openssl | 3.5.9-1~deb13u1 | — | Debian 13 base |
| CVE-2026-124709 | HIGH | libssl3t64 | 3.5.9-1~deb13u1 | — | Debian 13 base |
| CVE-2026-119373/4/9 | HIGH | libsqlite3-0 | 3.46.1-7+deb13u2 | — | Debian 13 base |
| CVE-2026-76642 / 78408–10 | HIGH | util-linux family | 2.41.5-… | — | Debian 13 base |
| CVE-2026-9538 | HIGH | perl-base | 5.40.1-6+deb13u1 | — (fix_deferred) | Debian 13 base |

Full before CSV: `%LOCALAPPDATA%\credit-scoring-mlops\block11-10\trivy-*-highcrit.csv`
After JSON: `trivy-after-credit-scoring-api_*.json`

## Remediation applied (minimal)

1. `docker/Dockerfile.models` — pin/upgrade OpenSSL Alpine packages to ≥3.5.9-r2.
2. `docker/Dockerfile.api` — switch builder/runtime to `python:3.12.16-slim-trixie`; `apt-get upgrade` on both stages.
3. `docs/docker_deployment.md` — base image note updated.

**Stopped further API hardening:** remaining 53 HIGH have **no FixedVersion** in current Trivy DB on Debian 13. Clearing them without weakening the gate requires a non-Debian/minimal runtime (distroless/Chainguard/Alpine Python) — beyond the 10‑minute compatible remediation budget and risks ORT wheel compatibility.

## Rebuilt tags / digests (local only)

| Image | Tag | Manifest digest |
|-------|-----|-----------------|
| api | `cloud-exp-20261126-155442-b713f2f-secfix` | `sha256:66be28cf8f8962022653416524e6f2f5de65eb8dc96b32bc20f3950ddabcad71` |
| models | `cloud-exp-20261126-155442-b713f2f-secfix` | `sha256:c9555e1ed5621cdf4df13080ae92075cb2d481be6d9c613591c2c2f9cbc4d085` |
| frontend | `cloud-exp-20261126-154419-b713f2f` (prior) | `sha256:2be133bb2514e8160fe37087c8067a399a0753d89c9c28ae6db69f24fca07306` |

Intended remote names (not pushed):

```text
ghcr.io/serg2311-prog/credit-scoring-api:cloud-exp-20261126-155442-b713f2f-secfix
ghcr.io/serg2311-prog/credit-scoring-models:cloud-exp-20261126-155442-b713f2f-secfix
ghcr.io/serg2311-prog/credit-scoring-frontend:cloud-exp-20261126-154419-b713f2f
```

## Verification

| Check | Result |
|-------|--------|
| Trivy models | **PASS** |
| Trivy api | **FAIL** (53 HIGH, 0 CRITICAL) |
| Smoke ready/info/predict | **PASS** (`mlp-onnx-fp32-v1`, p≈0.830205) |
| Protected SHA256 ×6 | **MATCH** |
| `git diff --check` Dockerfiles | **PASS** |
| `tests/ci/test_workflows.py` | **14 passed** |
| Packages scopes | Still missing → publish blocked |

## STOP GATE 1 decision

Publish still **blocked** until:

1. Operator adds `read:packages`/`write:packages`, **and**
2. Either accepts residual API OS HIGH (explicit) **or** authorizes distroless/Chainguard follow-up outside this timebox.
