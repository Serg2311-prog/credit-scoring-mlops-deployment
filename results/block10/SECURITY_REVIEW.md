# SECURITY REVIEW — Block 10

Read-only scan. **No secret values are printed in this report.**

## Scope

- Tracked files via `git ls-files` (456 text-ish files scanned; binaries skipped)
- Dockerfiles / Compose
- Terraform modules (static)
- GitHub Actions permissions (spot-check)
- Model registry write protection
- `.gitignore` for backups / personal paths
- Local Airflow demo credentials pattern

## Findings summary

| ID | Severity | Topic | Status |
| --- | --- | --- | --- |
| S-01 | — | AWS access-key / PEM private key patterns | **None found** in tracked text |
| S-02 | P3 | Local Airflow default password fallback | Present; labeled NOT production |
| S-03 | P2 | Absolute/personal path substrings | 2 scripts (sanitizer / stage); not credentials |
| S-04 | — | `_raw_encoding_backup` | Gitignored (confirmed in `.gitignore`) |
| S-05 | — | Production registry write | Fail-closed without `allow_production_write` |
| S-06 | — | Docker non-root | API `appuser`, frontend `nginx`, models UID, dvcdata `nobody` |
| S-07 | — | Trivy / security gate in CI | Present; Docker CI SUCCESS on baseline |
| S-08 | — | Unsafe production promotion | `auto_promote=false` across paths |
| S-09 | P1 | Primary CI workflows lack explicit `permissions:` | Inherit repo default token; CD workflows OK |

## Details

### Secrets / credentials

- Regex for common cloud keys and PEM headers: **0 hits**.
- Password-assignment heuristic hit: `scripts/airflow/entrypoint.sh` (local demo default). Acceptable for academic local stack; must not be reused for shared/cloud Airflow.
- No recommendation to rewrite git history (nothing critical discovered in tracked tip).

### PII

- Dataset described as UCI credit-card default features; README states no client PII in Git.
- Block 8 sanitation scripts exist; backups ignored.

### Docker

- Multi-stage API image drops pip/wheel; non-root USER; HEALTHCHECK present (`docker/Dockerfile.api`).
- Frontend HEALTHCHECK + `USER nginx`.

### Terraform (static)

- Modules for VPC, IAM, SG, managed K8s, object storage, monitoring patterns reviewed at architecture level.
- Credentials expected via env/provider — not hardcoded in modules (spot-check).
- `terraform apply` **not** executed in this audit.

### GitHub Actions

- Five primary CI workflows SUCCESS on `bdb8b43`.
- Synthetic artifacts generated in CI (does not publish production weights).
- Node 20 / cache warnings: deprecation noise, not exploitability.
- **P1:** `ci-python` / `ci-docker` / `ci-kubernetes` / `ci-infrastructure` / `ci-airflow-dag` omit top-level `permissions:` (confirmed by Infra/CI audit). CD paths set least-privilege scopes. Recommend `contents: read` (minimal) before shared-org use.

### Application controls

- `AB_ENABLED` default false (`src/api/settings.py`).
- `write_model_registry(..., allow_production_write=False)` raises on production path (`src/monitoring/ab_testing.py`).
- No production API e2e log-probe route found.

## Residual risk

Instructor/demo machines may keep local `.env` / cloud tokens **outside Git** — out of scope if gitignored. Ensure such files are never force-added.

## Verdict

**No P0 security blockers identified.** Remaining items are local-demo hygiene (P3) and path sanitization (P2).
