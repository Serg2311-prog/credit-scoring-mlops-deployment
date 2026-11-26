# REPRODUCIBILITY REPORT — Block 10.2

## Two timelines

### A — Baseline `bdb8b43` (Block 10 audit)

- README installed only `requirements-dev.txt` → clean pytest broken.
- No production models in Git.
- Drift exporter only on E2E overlay; API emitted fake-zero drift gauges.

### B — After Block 10.1/10.2 remediations (this tree)

- README matches CI requirement sets + synthetic note.
- Exporter on base observability; API has no drift gauges.
- Instructor pack documented + local ZIP (gitignored).
- Clean worktree verification executed (below).

## Clean environment (Block 10.2)

| Item | Detail |
| --- | --- |
| Location | `%TEMP%\cs-mlops-b102-clean2` |
| Method | `git worktree add --detach` @ `bdb8b43` + copy remediations; strip `*.onnx/*.pt/*.joblib` |
| Venv | New `.venv` in clone (not developer venv) |
| Deps | `requirements.txt` + `dev` + `api` + `nn` per README |
| Models | CI synthetic only |
| pytest | **232 passed, 6 skipped** after syncing working-tree `scripts/gpu_benchmark/run_benchmark.py` |
| Note | GPU runner Git content hash matches HEAD (`9936080f…`); index listing may show `H`. Transient clean-clone flake not treated as proven HEAD≠WT divergence |
| API ready | Synthetic → `model_not_ready` (expected vs production dim/contract) |
| Frontend / DVC | NOT_EXECUTED this block |

## Production path

Requires `artifacts/submission/instructor_model_pack.zip` (or equivalent) with verified SHA256. Unpacked FP32 holdout ROC-AUC matched **0.774154**.

## Classification

Reproducibility for **CI/synthetic** after remediations: **good**.
Reproducibility for **production inference** from GitHub alone: **requires instructor pack** (ACCEPTED_LIMITATION).
