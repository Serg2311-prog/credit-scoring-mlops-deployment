# Instructor model pack (production artifacts)

Production weights are **gitignored** and are **not** DVC pipeline outs. CI uses synthetic ONNX/joblib via `scripts/ci/generate_synthetic_artifacts.py`.

## Contents (do not commit without policy review)

| Relative path | Role | SHA256 (author baseline `bdb8b43` audit) |
| --- | --- | --- |
| `models/model_registry.json` | Registry (also tracked in Git) | `ffea203ba3e3854f7817b64f533ef8ee616cca6217096e6c6ab701dba6ce204d` |
| `models/credit_scoring_nn.pt` | PyTorch checkpoint | `d6e05563bb7790c34bf3e444db7c0e1d5ceea0aa92e26aa0b69f5d1f26d1c2ae` |
| `models/credit_scoring_nn.onnx` | Champion ONNX FP32 | `48051065162f98c0842f0f4bca80ce4105e343924a7b62001114c08adc7521a4` |
| `models/credit_scoring_nn.quant.onnx` | Experimental INT8 | `e4ceed53c08ad0fe9592563f05e11069c4db6aa5c1172c7ff55945df21c65954` |
| `models/preprocessor.joblib` | Sklearn preprocessor | `f949b92907853f09683ba0d82c9ec8aeb3d51bd6c06d37ffed82a8b867828b64` |

Approximate packed size (zip of binaries above): **~0.5–2 MB** depending on compression.

## Build the pack (author machine)

CLI: no arguments. Run from the **repository root** with the five production files already present under `models/` (paths must match the table). The script does not accept an output path override.

```powershell
python scripts/block10/build_instructor_model_pack.py
```

What it writes (all gitignored under `artifacts/submission/`):

| Output | Role |
| --- | --- |
| `artifacts/submission/instructor_model_pack.zip` | Archive with POSIX entries `models/...`, plus `SHA256SUMS.txt` and a short `README.md` **inside** the ZIP |
| `artifacts/submission/instructor_model_pack_meta.json` | Sidecar with `zip_sha256`, size, and per-file sums (printed to stdout as JSON) |

Zip entry layout matches repo-relative paths (`models/credit_scoring_nn.onnx`, …). Do **not** commit the ZIP or meta JSON.

## Safe transfer

1. Author runs `scripts/block10/build_instructor_model_pack.py` from repo root.
2. Verify file hashes against the table and/or `SHA256SUMS.txt` inside the ZIP; optionally check `zip_sha256` in the meta JSON.
3. Share via private LMS / encrypted channel / in-person USB — **not** a public gist.
4. Recipient unpacks the ZIP **at the repository root** of a clean clone (so files land in `models/…`). Do not unpack into a nested folder that would create `models/models/…`.
5. Do **not** replace files with CI synthetic artifacts when validating production parity.

## Without the pack

```bash
pip install -r requirements.txt -r requirements-dev.txt -r requirements-api.txt -r requirements-nn.txt
# Only if production ONNX is absent; omit --force to avoid overwriting non-synthetic models.
python scripts/ci/generate_synthetic_artifacts.py --output-dir models
pytest -m "not k8s and not e2e" -q
```

Synthetic weights pass CI gates but **do not** match the SHA256 table.
