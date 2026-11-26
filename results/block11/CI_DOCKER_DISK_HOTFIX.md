# CI Docker disk hotfix — Block 11 follow-up

**Branch:** `fix/ci-docker-disk-space`
**Trigger evidence:** GitHub Actions run `45843958855` (push to `main` after PR #1)

## Root cause

All four image builds, all Trivy scans/JSON reports, artifact upload, and the CRITICAL/HIGH security gate **succeeded**.

The job then failed in **Post Set up Python** while saving the **pip cache**:

```text
tar --posix -cf cache.tzst ... --use-compress-program zstdmt
zstd: error 70 : Write error : cannot write block : No space left on device
##[error]No space left on device : '.../_diag/blocks/...'
```

Disk was exhausted by the combination of:

1. Full `pip` install of `requirements.txt` + `requirements-api.txt` + `requirements-nn.txt` (includes **torch**) solely to generate small synthetic ONNX/joblib artifacts.
2. `actions/setup-python` **`cache: pip`** attempting a large post-job cache archive.
3. Four local Docker images + Buildx/buildkit cache + Trivy vulnerability DB on a constrained `ubuntu-latest` runner.

## Changes (`.github/workflows/ci-docker.yml` only)

| Change | Why |
|--------|-----|
| Pre-job free of unused runner toolchains (dotnet, Android, GHC, CodeQL, …) + `docker image/builder prune` | Recover multi‑GB before builds |
| `df -h` / `df -i` / `docker system df` before prune, before builds, after builds, after cleanup | Diagnose future ENOSPC |
| `cache: false` on `setup-python` | Eliminate failing post-job pip cache save (direct cause of 45843958855) |
| `pip install --no-cache-dir` | Avoid local pip wheel cache growth |
| Post security-gate Docker cleanup (`if: always()`, `continue-on-error: true`) | Free images/buildx **after** Trivy + gate; must not mask gate FAILURE or fail a green job |

## Unchanged

- All four images still built and scanned
- Trivy CRITICAL/HIGH + `ignore-unfixed: true`
- Security gate logic
- Action pin SHAs / versions
- Dockerfiles, models, app, Terraform, other workflows

## Hosted verification plan

1. Open PR from `fix/ci-docker-disk-space` → `main` (or push after commit approval).
2. Confirm **CI Docker** green on the PR.
3. Merge and confirm **CI Docker** green on `main` (the failure mode was post-merge on `main`).
4. In logs, confirm: disk groups show free space; **no** “Post Set up Python” cache save; security gate still prints outcomes for api/models/frontend/dvc.

## Remaining limitations

- Problem is **not** declared permanently fixed until hosted CI on this branch/`main` succeeds.
- Runner free space still finite; Trivy DB + four images remain heavy.
- Synthetic artifact step still installs torch (functional necessity of current script); only caching/disk hygiene changed.
