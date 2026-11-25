# Block 8.1 evidence sanitation

Published copies under `results/block8/` were sanitized before commit:

1. **Encoding:** UTF-16 / UTF-8-BOM → UTF-8 without BOM.
2. **Paths:** absolute project paths → repo-relative; other local absolute paths → `<REDACTED_PATH>`.
3. **Metrics / SHA256 / timestamps / statuses:** unchanged except path strings.

## Original bytes

Encoding originals (pre-conversion) are preserved locally as:

`results/block8/_raw_encoding_backup/*.orig`

That directory is **gitignored** (contains unsanitized absolute paths). Each converted file lists `original_sha256` in `sanitation_summary.json`.

Published UTF-8 copies under `results/block8/` (excluding `_raw_encoding_backup/`) are the review/commit artifacts.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts\block8\sanitize_block8_evidence.py --force-restore
```
