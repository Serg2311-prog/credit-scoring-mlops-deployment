# FINAL ACCEPTANCE REPORT — Block 10.2

**Baseline (audit):** `bdb8b43cf3a20fb58eaa8da7997862d5ac748b5a`
**Tree under review:** baseline + Block 10.1/10.2 remediations (**uncommitted**)
**No commit/push. No retrain. No terraform apply.**

## 1. Scope

Block 10.2 technical acceptance after remediations. Historical findings: `FINDINGS.md`.

## 2. Quantized ROC-AUC proof

| Field | Value |
| --- | --- |
| Command | `PYTHONPATH=. python scripts/block10/eval_quant_holdout_proof.py` |
| Artifact | `results/block10/quant_roc_auc_proof_block102.json` |
| Python | 3.13.7 |
| ONNX Runtime | 1.32.0 |
| Quant SHA256 | `e4ceed53c08ad0fe9592563f05e11069c4db6aa5c1172c7ff55945df21c65954` |
| Preprocessor SHA256 | `f949b92907853f09683ba0d82c9ec8aeb3d51bd6c06d37ffed82a8b867828b64` |
| Holdout | `data/processed/test.csv` n=6000; split test_size=0.2, random_state=42 |
| Threshold | 0.5 |
| **Quant ROC-AUC** | **0.7732256250573489** |
| FP32 ROC-AUC | 0.774154013072903 |
| Decision flips | 75 / 6000 (1.25%) |

Historical `0.7720` / `0.7736` **not overwritten**. ORT-version difference is a **possible** cause, not a controlled fact.

## 3. Instructor model pack

| Field | Value |
| --- | --- |
| Path | `artifacts/submission/instructor_model_pack.zip` (**gitignored**) |
| Size | **140061** bytes |
| ZIP SHA256 | `faa23e3c60bd1653adea3dd25cfe6071f4db4b86839b3ca60731e9fa217aee55` |
| Verify | Unpack + SHA256SUMS OK; unpacked FP32 holdout ROC-AUC 0.774154 |
| Caution | Contains trusted serialized artifacts including **joblib** — use only after provenance + checksum verification |

## 4. Clean environment

| Step | Result |
| --- | --- |
| Method | `git worktree` @ `bdb8b43` + copy remediations; **no** production ONNX/PT/joblib |
| Fresh venv | Yes (not developer `.venv`) |
| README deps install | EXECUTED_PASS |
| Synthetic artifacts | EXECUTED_PASS |
| pytest | **232 passed, 6 skipped** (synthetic path in isolated worktree) |
| GPU runner Git consistency | **VERIFIED** — `git ls-files -v` shows `H`; `git rev-parse HEAD:scripts/gpu_benchmark/run_benchmark.py` equals `git hash-object` working tree (`9936080f…306be98b`). An earlier clean-clone flake involved a different worktree snapshot; root cause of that transient mismatch is **not** asserted as proven. |
| API `/health/ready` with synthetic | model_not_ready (dim/contract) — **not** production pack |
| Frontend / DVC demo | **NOT_EXECUTED** (RAM after obs stack) |

## 5. Observability runtime (base stack, no E2E overlay)

| Check | Result |
| --- | --- |
| Compose up | EXECUTED_PASS |
| Exporter :9108 | up; status=1.0; share=0.25 from isolated artifacts |
| Prometheus scrape | drift-metrics-exporter **up** |
| API fake zeros | **absent** (`ml_data_drift_share` not on API) |
| Unavailable path | local resolve → status unavailable, no share series |
| Stack stopped | EXECUTED_PASS |
| Evidence | `results/block10/obs_runtime_verification.json` |

## 6. HPA

| Check | Result |
| --- | --- |
| Static | EXECUTED_PASS — `results/block10/hpa_verification.json` |
| Runtime scale | **NOT_EXECUTED** (no Metrics Server / kind in 10.2) |

## 7. Final gates (developer tree + remediations)

| Gate | Result |
| --- | --- |
| pytest | **236 passed, 2 skipped** |
| Black | PASS |
| Flake8 | PASS |
| Compose config | PASS |
| kustomize production | PASS (includes HPA) |
| Secrets scan (tracked) | no AWS/PEM hits |
| git diff --check | PASS (CRLF warnings only) |
| Protected SHA256 ×6 | **unchanged** |
| Block7/8 git trees | **unchanged** |

## 8. Remaining limitations

1. Production binaries not in Git — use instructor pack privately.
2. Cloud `terraform apply` NOT_EXECUTED.
3. kind NetworkPolicy enforcement unproven.
4. HPA runtime unproven (Metrics Server).
5. Frontend/DVC not re-demoed in clean clone this block.
6. GPU runner remains flagged `H` in the index listing; content hash matches HEAD (no content edit required for evidence consistency).

## 9. Changed / new files (remediation + 10.2)

**Modified (tracked):** workflows (permissions), README, compose obs, prometheus, grafana, metrics/export, tests, docs metrics/runbooks, kustomization, `.gitignore`.

**New (to commit):** `docs/instructor_model_pack.md`, `k8s/overlays/production/hpa-api.yaml`, `scripts/block10/*`, `results/block10/*` (reports; not the ZIP).

**Deleted:** none of protected evidence; removed dead API drift gauges / e2e exporter duplicate / dead env.

**Do not commit:** `artifacts/submission/instructor_model_pack.zip`, TZ extract, credentials, absolute-path backups.

## 10. Git snapshot (at acceptance write-up)

Run locally for exact current lines:

```text
git status --short
git diff --stat HEAD
```

(Working tree dirty with remediations + `?? results/block10/` + `?? docs/instructor_model_pack.md` + `?? k8s/.../hpa-api.yaml` + `?? scripts/block10/`.)

## Verdict

Technical acceptance complete with documented limitations.
