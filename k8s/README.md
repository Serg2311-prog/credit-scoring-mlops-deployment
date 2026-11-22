# Kubernetes (Stage 3A) — local kind

Local single-node deployment of the stage-2 FastAPI ONNX API.

## Prerequisites

- Docker Desktop (Linux containers)
- `kubectl`
- `kind` (portable binary under `tools/kind.exe` or on PATH)

Install kind (Windows, user-local):

```powershell
New-Item -ItemType Directory -Force -Path tools | Out-Null
curl.exe -fsSL -o tools\kind.exe https://kind.sigs.k8s.io/dl/v0.29.0/kind-windows-amd64
.\tools\kind.exe version
```

## Quick path

```powershell
.\scripts\k8s_create.ps1
.\scripts\k8s_build_load.ps1
.\scripts\k8s_deploy.ps1
.\scripts\k8s_smoke.ps1
```

Destroy (asks for confirmation):

```powershell
.\scripts\k8s_destroy.ps1
```

## Model delivery

1. Build `credit-scoring-models:stage3a` from `docker/Dockerfile.models` (copies local `models/*.onnx` + `preprocessor.joblib`).
2. `kind load docker-image` both API and models images.
3. Init container `copy-models` copies artifacts into an `emptyDir` volume.
4. API container mounts `/app/models` **read-only**.

No Windows `hostPath`, no ConfigMap/Secret for binaries, no public model download.

## Access

```powershell
kubectl -n credit-scoring port-forward svc/credit-scoring-api 8000:8000
```

## Render manifests

```powershell
kubectl kustomize k8s/overlays/local
```
