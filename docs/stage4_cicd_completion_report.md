# Stage 4 / Block 5 + 5.1 — CI/CD Staging & Production Completion Report

**Date:** 2026-11-24
**Working tree:** Block 5 accepted + Block 5.1 acceptance fixes (no commit/push)
**Cloud terraform apply / YC Managed K8s:** **NOT_EXECUTED** (policy)

## Status legend

| Status | Meaning |
| --- | --- |
| IMPLEMENTED | Code/workflows present |
| VERIFIED_STATIC | YAML/kustomize/unit tests without cluster |
| VERIFIED_LOCAL | Executed on local kind |
| VERIFIED_CI | Observed green on GitHub Actions |
| VERIFIED_CLOUD | Real cloud deploy |
| NOT_EXECUTED | Intentionally not run |

## Block 5.1 acceptance fixes

| # | Remark | Resolution | Status |
| --- | --- | --- | --- |
| 1 | Required CI gate | Five workflows including **CI Airflow DAG**; workflow-run API; missing/pending/failed/cancelled/skipped/stale tip/reruns | IMPLEMENTED + VERIFIED_STATIC |
| 2 | Auto staging | `workflow_run` on main + `vars.AUTO_STAGING_ENABLED=true`; tip-of-main; SHA concurrency; no PR; manual dispatch retained | IMPLEMENTED (hosted auto **NOT_EXECUTED**) |
| 3 | Staging→prod provenance | `staging-release.json` + fetch/verify in `cd-production.yml`; digests only from trusted run | IMPLEMENTED + VERIFIED_STATIC |
| 4 | Fail-closed deploy | Modes `validation` / `publish` / `deploy`; missing kube/smoke vars → exit 1 on deploy | IMPLEMENTED + VERIFIED_STATIC |

## 1. Architecture (after 5.1)

```
CI Python / Docker / Infra / K8s / Airflow DAG
        │
        ▼
check_required_ci.py (same git SHA; tip-of-main on auto)
        │
        ▼
ci-cd.yml  mode=validation | publish | deploy
        ├ validation: render only
        ├ publish: GHCR SHA+digest + publish-only manifest (not prod-eligible)
        └ deploy: kube apply + mandatory smoke + staging-release.json (staging_verified)
                │
                ▼
cd-production.yml  staging_run_id → fetch manifest → same digests
        ├ validation: render only
        └ deploy: fail-closed kube + mandatory smoke (Environment: production)
```

**Auto staging:** enabled only when repository variable `AUTO_STAGING_ENABLED=true`.
Otherwise `workflow_run` exits with skip notice (not a deployment success claim).

**Registry:** GHCR. Deploy via `@sha256:…`. `:latest` forbidden.

## 2. GitHub Environments / Secrets / Variables

| Scope | Name | Purpose |
| --- | --- | --- |
| Repo variable | `AUTO_STAGING_ENABLED` | Opt-in auto staging (`true` / unset) |
| Env `staging` secret | `STAGING_KUBECONFIG` | Required for `mode=deploy` |
| Env `staging` vars | `STAGING_SMOKE_BASE_URL`, `STAGING_SMOKE_HOST` | Required for `mode=deploy` smoke |
| Env `production` secret | `PRODUCTION_KUBECONFIG` | Required for production `mode=deploy` |
| Env `production` vars | `PRODUCTION_SMOKE_BASE_URL`, `PRODUCTION_SMOKE_HOST` | Required for production smoke |

Configure Environment **required reviewers** for `production` in UI. **Not claimed configured.**

## 3. Staging release manifest

Artifact name: `staging-release-<sha>` containing `staging-release.json`:

- `schema`: `credit-scoring.staging-release.v1`
- `git_sha`, image digests (api/models/frontend)
- `staging_workflow_run_id`, `staging_workflow_name`
- `smoke.ok`, `status`: `staging_verified` (deploy) or `published_not_deployed` (publish)

Production **rejects** publish-only manifests, wrong SHA, digest substitution, failed smoke, missing artifact, unsuccessful staging run.

## 4. Local kind verification (Block 5 — unchanged mechanism)

**VERIFIED_LOCAL** evidence: `artifacts/ci/local_cd/` (tag `cd-20261124110017`).
Block 5.1 did not change the kind apply path; full kind E2E **not re-run**.

## 5. Hosted / cloud

| Item | Status |
| --- | --- |
| Prior CI 5/5 | VERIFIED_CI (historical) |
| New `ci-cd` / `cd-production` on Actions | NOT_EXECUTED (no commit/push) |
| GHCR push / cloud kube | NOT_EXECUTED |
| terraform apply | NOT_EXECUTED |

## 6. Rollback

1. Promote prior `staging-release.json` digests via `cd-production.yml` with that staging run id.
2. Or `kubectl -n <ns> rollout undo deploy/credit-scoring-api`.
3. Re-run `scripts/ci/smoke_http.py`.
