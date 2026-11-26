# Docker Deployment — Inference API

**Block 11.15 delivery:** `docker/Dockerfile.api` restored to **exact `main` content** (`python:3.12-slim-bookworm`). The experimental trixie remediation is **not** part of the final delivery; historical scan results remain in [`results/block11/IMAGE_BUILD_REPORT.md`](../results/block11/IMAGE_BUILD_REPORT.md) (53 HIGH / 0 CRITICAL without FixedVersion on the experiment image). Merge-prep Trivy gate (`CRITICAL,HIGH` + `ignore-unfixed`, matching `ci-docker.yml`): API/models/frontend **PASS**. Models image keeps Alpine openssl bump (`Dockerfile.models`). See [`results/block11/MERGE_READINESS_REPORT.md`](../results/block11/MERGE_READINESS_REPORT.md).

## Image

- File: `docker/Dockerfile.api`
- Base (delivery): `python:3.12-slim-bookworm` (CPU-only, no CUDA/PyTorch) — identical to `main`
- Multi-stage build with venv
- Non-root user `appuser` (uid 10001)
- Runtime deps: `requirements-api.txt`
- Artifacts **not** baked into image; mounted read-only

## Compose

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail 100
docker compose down
```

Service `api`:

- Port `8000:8000`
- Healthcheck on `/health/ready`
- `mem_limit: 1536m`, `cpus: 1.0`
- Volumes:
  - `./models/credit_scoring_nn.onnx:/app/models/credit_scoring_nn.onnx:ro`
  - `./models/preprocessor.joblib:/app/models/preprocessor.joblib:ro`

If artifacts missing, readiness returns 503 (no fake predictions).

## Environment

See `.env.example`. Threshold remains `0.5`.

## Verified locally (2026-11-22)

- `docker compose build` → PASS (`credit-scoring-api:stage2`)
- `docker compose up -d` → healthy
- HTTP smoke inside container → PASS
- Container memory ≈ **139.7 MiB / 1.5 GiB**
- `docker compose down` → PASS

## Kubernetes readiness (stage 3+)

Current probes map to:

- liveness → `GET /health/live`
- readiness → `GET /health/ready`
- metrics scrape → `GET /metrics`
