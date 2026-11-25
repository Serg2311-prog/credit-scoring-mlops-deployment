# BLOCK 9 — Acceptance Report

**Date:** 2026-11-25
**Baseline HEAD:** `0df191a`
**Commit/push:** not performed

---

## Created / updated documents

| Path | Action |
| --- | --- |
| `README.md` | Rewritten (RU entrypoint, verified commands) |
| `docs/architecture/overview.md` | 7 Mermaid diagrams + local vs cloud split |
| `docs/requirements_matrix.md` | TZ 50-point mapping + status vocabulary |
| `docs/final_project_report.md` | **Created** (20 sections) |
| `docs/evidence_index.md` | **Created** |
| `docs/quick_review.md` | **Created** (reviewer path, 8 GB) |
| `docs/defense_guide.md` | **Created** (demo + 20 Q&A) |
| `infra/terraform/**/backend*.example` | Removed unsafe CLI `access_key`/`secret_key` guidance |
| `results/block9/*` | SHA gates, pytest/lint logs, this report |

## Contradictions found and fixed

1. README still pointed to older stage narrative / commit `65de3ad` as primary status → aligned to `0df191a` and Block 7–8.1 evidence.
2. Terraform examples suggested `-backend-config=access_key/secret_key` → replaced with **env-only** credentials.
3. Requirements matrix statuses mixed old labels → replaced with VERIFIED_* / OPTIONAL vocabulary from Block 9 spec.
4. Architecture overview incomplete for monitoring/drift/A/B → expanded Mermaid set (7 diagrams).

## Functional issues

**None discovered that require code changes.** Documentation-only block; no silent feature fixes.

## Checks

| Check | Result |
| --- | --- |
| Relative Markdown links (README+docs) | **0 missing** (74 checked) |
| Mermaid blocks in overview | **7**, crude syntax OK |
| `pytest -m "not k8s and not e2e"` | **231 passed, 2 skipped** |
| Black CI scope | **PASS** |
| Flake8 CI scope | **PASS** |
| `git diff --check` | **PASS** |
| Secrets/PII scan (docs/TF examples) | **0 secrets**, **0 abs user paths**, **0 affirmative CLI secret init** |
| Production SHA256 6/6 | **unchanged** |
| `results/block7` | **clean** (unchanged) |
| `results/block8` | **clean** (unchanged) |
| `_raw_encoding_backup` gitignored | **yes** |

## Remaining limitations (honest)

- No `terraform apply` / paid cloud / live remote state
- No hosted cloud staging/production deploy
- No cloud GPU node group runtime
- NetworkPolicy kind enforcement not runtime-proven
- No GPU INT8 / GPU HTTP load
- Online A/B uses quantized ONNX challenger; synthetic HTTP
- cAdvisor Docker Desktop label limits
- Airflow E2E local only; `auto_promote=false`
- Optional: Seldon, shadow, Istio, Redis/geo — not implemented

## Preliminary TZ mapping (not mentor grade)

| Stage | Max | Evidence posture |
| --- | ---: | --- |
| Model | 5 | VERIFIED_LOCAL + VERIFIED_GPU |
| Cloud | 7 | validate VERIFIED; apply NOT_EXECUTED |
| Containers/K8s | 8 | VERIFIED_LOCAL; NP partial |
| CI/CD | 5 | VERIFIED_CI |
| Monitoring | 8 | VERIFIED_LOCAL |
| Drift | 7 | VERIFIED_LOCAL |
| Automation | 5 | VERIFIED_LOCAL (optional scaling absent) |
| Docs | 5 | Block 9 package |
| **Total max** | **50** | *(mentor decides)* |

## Git

See `results/block9/git_status.txt` / `git_diff_stat.txt` after final save.
**No commit/push. No Block 10.**
