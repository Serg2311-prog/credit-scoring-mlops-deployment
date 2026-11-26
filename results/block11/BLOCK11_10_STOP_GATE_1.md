# BLOCK 11.10 — STOP GATE 1 (after Trivy remediation)

**Branch:** `cloud-deployment`
**GHCR owner:** `serg2311-prog` (repo PRIVATE)
**Publish:** **NOT EXECUTED** — waiting for separate operator approval.

## Hard publish blockers

1. **Token scopes:** `gist`, `read:org`, `repo`, `workflow` only — **no** `read:packages` / `write:packages`. Agent does not mint tokens.
2. **Trivy API:** still **FAIL** (53 HIGH, FixedVersion empty on Debian 13). Gate not weakened.

## Trivy before → after

| Image | Before | After |
|-------|--------|-------|
| **models** | FAIL 2 HIGH (OpenSSL 3.5.9-r0) | **PASS 0** |
| **api** | FAIL 102 (2 CRITICAL + 100 HIGH, bookworm, no fixes) | FAIL **53 HIGH / 0 CRITICAL** (trixie, no FixedVersion) |
| **frontend** | PASS | PASS (not rebuilt) |

### Models CVEs (before — fixed)

| CVE | Sev | Pkg | Installed | Fixed | Source |
|-----|-----|-----|-----------|-------|--------|
| CVE-2026-124709 | HIGH | libssl3 / libcrypto3 | 3.5.9-r0 | 3.5.9-r2 | Alpine base |

### API remaining (after) — all OS, Fixed empty

All 53 findings are **Debian 13 system packages** (util-linux family, openssl/libssl3t64, sqlite, ncurses, perl-base, …). **0** Python-library HIGH/CRITICAL. Clearing without ignore flags needs non-Debian minimal base (distroless/Chainguard) — stopped per 10‑minute / compatibility budget.

## Remediation done

- `Dockerfile.models`: force OpenSSL ≥3.5.9-r2
- `Dockerfile.api`: `python:3.12.16-slim-trixie` + `apt-get upgrade`
- Docs note in `docs/docker_deployment.md`

## Local images (secfix tag)

```text
credit-scoring-api:cloud-exp-20261126-155442-b713f2f-secfix
  digest sha256:66be28cf8f8962022653416524e6f2f5de65eb8dc96b32bc20f3950ddabcad71
credit-scoring-models:cloud-exp-20261126-155442-b713f2f-secfix
  digest sha256:c9555e1ed5621cdf4df13080ae92075cb2d481be6d9c613591c2c2f9cbc4d085
credit-scoring-frontend:cloud-exp-20261126-154419-b713f2f
  digest sha256:2be133bb2514e8160fe37087c8067a399a0753d89c9c28ae6db69f24fca07306

→ ghcr.io/serg2311-prog/credit-scoring-{api,models,frontend}:…
```

## Other verification

| Check | Result |
|-------|--------|
| Smoke ready / info / predict | PASS (`mlp-onnx-fp32-v1`, p=0.830205) |
| ONNX parity (logit→sigmoid vs `/predict`) | **PASS** abs_delta=0 |
| Protected SHA256 ×6 | MATCH |
| `git diff --check` Dockerfiles | PASS |
| `tests/ci/test_workflows.py` | 14 passed |

Details: `results/block11/IMAGE_BUILD_REPORT.md`, `application_verification_summary.json`.

## Operator choices

1. **ADD_PACKAGE_SCOPES** + **APPROVE_PUBLISH_ACCEPT_API_TRIVY_RESIDUAL** — push secfix digests to private GHCR despite 53 OS HIGH.
2. **AUTHORIZE_DISTROLESS_FOLLOWUP** — larger base change to chase empty-FixedVersion CVEs (outside this gate).
3. **ABORT_CLOUD_APP**

**No push / kubectl / commit until you explicitly approve.**
