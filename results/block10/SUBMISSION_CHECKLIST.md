# SUBMISSION CHECKLIST — Block 10.2

> **Block 11.14:** cloud experiment completed (apply→destroy; app ABORT). Use [`../block11/MERGE_READINESS_REPORT.md`](../block11/MERGE_READINESS_REPORT.md) and [`../block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](../block11/FINAL_CLOUD_EXPERIMENT_REPORT.md) for current cloud/merge status. This Block 10 checklist is retained as historical.

## Status: READY_FOR_SUBMISSION

### Before commit (author)

- [ ] Review `git status --short` / `git diff --stat`
- [ ] GPU runner: content hash matches HEAD (verified); no content change required for Block7 SHA gate
- [ ] Commit remediations + `results/block10/` reports (optional) — **not** the model ZIP
- [ ] Confirm `.gitignore` covers `artifacts/submission/`
- [ ] Prepare private transfer of `artifacts/submission/instructor_model_pack.zip`

### Give the instructor

1. GitHub repo + commit after remediation push (or patch vs `bdb8b43`)
2. Actions links for CI on that commit
3. Instructor model pack ZIP + ZIP SHA256 `faa23e3c…217aee55` (offline)
4. Point to `docs/instructor_model_pack.md` and `results/block10/FINAL_ACCEPTANCE_REPORT.md`

### Do not claim

- Live Yandex Cloud production
- kind NP enforcement proven
- HPA live autoscaling observed in Block 10.2
- Synthetic models = production SHA

### Finding statuses (summary)

| ID | Status |
| --- | --- |
| F-P1-01 | FIXED_AND_VERIFIED |
| F-P1-02 | ACCEPTED_LIMITATION (+ instructor pack) |
| F-P1-03 | FIXED_AND_VERIFIED |
| F-P1-04 | FIXED_AND_VERIFIED |
| F-P2-01 | FIXED_AND_VERIFIED |
| F-P2-02 | FIXED_AND_VERIFIED (static); runtime NOT_EXECUTED |
| F-P2-03 | ACCEPTED_LIMITATION |
| F-P2-04 | ACCEPTED_LIMITATION |
| F-P2-05 | ACCEPTED_LIMITATION |
| F-P2-06 | FIXED_AND_VERIFIED |
| F-P2-07 | FIXED_AND_VERIFIED |
| F-P2-08 | ACCEPTED_LIMITATION |
| F-P2-09 | ACCEPTED_LIMITATION |
| F-P3-01..03,05 | ACCEPTED_LIMITATION |
| F-P3-04 | FIXED_AND_VERIFIED |
