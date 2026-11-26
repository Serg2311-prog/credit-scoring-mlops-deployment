# Kubernetes Local Deployment (Stage 3A)

Локальный single-node кластер **kind** для FastAPI ONNX inference API (этап 2).  
Без Ingress, Service Mesh, Prometheus Operator, Terraform и облака.

## Архитектура

```text
Windows host
  └─ Docker Desktop
       └─ kind node (control-plane)
            └─ Namespace credit-scoring
                 ├─ ConfigMap  credit-scoring-api-config
                 ├─ Deployment credit-scoring-api (replicas=1)
                 │    ├─ init: copy-models  (image credit-scoring-models:stage3a)
                 │    └─ container: api     (image credit-scoring-api:stage3a)
                 │         mounts: emptyDir /app/models (ro), /tmp
                 └─ Service ClusterIP :8000
                      └─ kubectl port-forward → localhost:8000
```

## Требования

| Инструмент | Проверено |
| --- | --- |
| Docker Desktop | Linux containers |
| kubectl | bundled with Docker Desktop |
| kind | `tools/kind.exe` (portable) или PATH |

### Установка kind (без админа)

```powershell
New-Item -ItemType Directory -Force -Path tools | Out-Null
curl.exe -fsSL -o tools\kind.exe https://kind.sigs.k8s.io/dl/v0.29.0/kind-windows-amd64
.\tools\kind.exe version
```

Не меняйте глобальные настройки Docker Desktop ради этого этапа.

## Доставка модели

1. Локально должны существовать `models/credit_scoring_nn.onnx` и `models/preprocessor.joblib` (не в Git).
2. `docker/Dockerfile.models` собирает образ `credit-scoring-models:stage3a` только с этими файлами.
3. `kind load docker-image` загружает API и models образы в node.
4. Init container копирует файлы в `emptyDir`.
5. API монтирует `/app/models` **read-only**.

**Запрещено:** Windows `hostPath`, ConfigMap/Secret для бинарников, скачивание из недоверенных URL.

При отсутствии артефактов в models-образе Pod не станет Ready (`/health/ready` → 503).

## ConfigMap / Secret

ConfigMap (`k8s/base/configmap.yaml`) — несекретные env, совпадают с этапом 2:

- `MODEL_VERSION=mlp-onnx-fp32-v1`
- `MODEL_BACKEND=onnx`
- `PREDICTION_THRESHOLD=0.5`
- `MAX_BATCH_SIZE=256`
- `ORT_*`, пути, `LOG_LEVEL`

Secret: для serving не требуется. Пример: `k8s/base/secret.example.yaml` (не применяется Kustomize).

## Probes

| Probe | Path | Назначение |
| --- | --- | --- |
| startupProbe | `/health/live` | процесс поднялся (до 60 с) |
| livenessProbe | `/health/live` | без inference |
| readinessProbe | `/health/ready` | модель+preprocessor загружены |

## Resources (local overlay)

```yaml
requests: { cpu: 100m, memory: 256Mi }
limits:   { cpu: "1",  memory: 512Mi }
```

Ориентир по этапу 2: контейнер ~140 MiB, uvicorn RSS ~200 MB. При OOMKilled — поднять limit и зафиксировать в отчёте.

## Rollout strategy

```yaml
rollingUpdate:
  maxSurge: 0
  maxUnavailable: 1
```

На ноутбуке с 1 репликой и ограниченной RAM это избегает двух Pod одновременно.  
Компромисс: **кратковременная недоступность** при обновлении. Zero-downtime **не** заявляется.

Rollback:

```powershell
.\scripts\k8s_rollback.ps1
# или
kubectl -n credit-scoring rollout undo deployment/credit-scoring-api
```

## Команды

```powershell
.\scripts\k8s_create.ps1
.\scripts\k8s_build_load.ps1
.\scripts\k8s_deploy.ps1
.\scripts\k8s_smoke.ps1
.\scripts\k8s_rollback.ps1

kubectl kustomize k8s/overlays/local
kubectl -n credit-scoring port-forward svc/credit-scoring-api 8000:8000
```

Удаление кластера (явное подтверждение):

```powershell
.\scripts\k8s_destroy.ps1 -Confirm credit-scoring
```

## Troubleshooting

| Симптом | Что проверить |
| --- | --- |
| ImagePullBackOff | `.\scripts\k8s_build_load.ps1` выполнен? tag `stage3a`? |
| Init crash | есть ли оба файла в `models/` при build models image? |
| Ready=False | `kubectl -n credit-scoring logs deploy/credit-scoring-api` |
| OOMKilled | `kubectl -n credit-scoring describe pod ...` → поднять memory limit |
| port-forward refused | Deployment Available? `kubectl get pods -n credit-scoring` |

## Ограничения Stage 3A

- Только локальный kind, 1 replica
- Нет Ingress / LB / mesh
- Нет Prometheus Operator / Grafana
- Нет облачных ресурсов
- Staging/production overlays — позже

## Historical Stage 3A validation snapshot (2026-11-22)

kind v0.29.0 + node v1.33.1 tooling used for local Kustomize/API deployment validation. Ingress/NetworkPolicy follow-ups are covered in Stage 3 completion and this runbook.
