# Terraform Infrastructure — Yandex Cloud (Этап 2 / historically Stage 3B)

**Статус (Block 11.14):** `cloud-experiment` **применён, runtime-проверен и уничтожен** (Remote State + Apply + MK8s → Destroy + YC empty checks).
Staging/production roots по-прежнему без apply.
Исторический Stage 3B отчёт (до cloud apply): [`docs/stage2_infrastructure_completion_report.md`](stage2_infrastructure_completion_report.md).
Финальный отчёт: [`results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md`](../results/block11/FINAL_CLOUD_EXPERIMENT_REPORT.md).

**Network module:** все SG rules только через `yandex_vpc_security_group_rule` (без inline); 12 rules мигрированы; dependency guard перед destroy. Plan перед guard: 1 add / 0 change / 0 destroy.

## Архитектура модулей

```text
environments/{staging|production|cloud-experiment}
    → module.network
    → module.iam
    → module.monitoring   (optional in cloud-experiment)
    → module.registry     (optional in cloud-experiment)
    → module.storage      (optional in cloud-experiment)
    → module.kubernetes  (depends on network + iam [+ monitoring log group])
           ├ cpu node group (default)
           └ gpu node group (enable_gpu_node_group=false by default)
```

| Модуль | Ресурсы | Назначение |
| --- | --- | --- |
| `network` | `yandex_vpc_network`, `yandex_vpc_subnet`, SG + rule | VPC, CIDR, master/nodes SG |
| `iam` | SA + `folder_iam_member` | least privilege |
| `kubernetes` | cluster + CPU NG + optional GPU NG (`count`) | MK8s CALICO; GPU opt-in |
| `registry` | `yandex_container_registry` | API + models images |
| `storage` | `yandex_storage_bucket`, optional `yandex_kms_symmetric_key` | private ML artifacts |
| `monitoring` | `yandex_logging_group` | master/app logs retention (metrics → Stage 5) |

Provider: `yandex-cloud/yandex` `~> 0.250`
Terraform: `>= 1.5.0` (проверено с **v1.17.2**)

## Staging vs production

| | Staging | Production |
| --- | --- | --- |
| prefix | `cs-stg` | `cs-prod` |
| CIDR | `10.20.0.0/24` | `10.30.0.0/24` |
| nodes | 1 × 2 vCPU / 4 GB, preemptible | 2 × 2 vCPU / 8 GB, non-preemptible |
| release channel | REGULAR | STABLE |
| log retention | 7 days | 30 days |
| state | отдельный backend key/bucket | отдельный backend key/bucket |
| folder | желательно отдельный folder | желательно отдельный folder |

Окружения **не** шарят state и **не** шарят CIDR.

## IAM (границы)

| SA | Роли | Не выдаётся |
| --- | --- | --- |
| k8s-cluster | `k8s.clusters.agent`, `vpc.publicAdmin`, `container-registry.images.puller`, `logging.writer`, optional `load-balancer.admin` | `editor`/`admin` |
| k8s-nodes | puller + `logging.writer` | admin |
| ml-reader | `storage.viewer` | `storage.admin` |
| registry-pusher | `container-registry.images.pusher` | folder editor |

Долгоживущие static keys **не** создаются модулем. Для Object Storage bucket management provider использует IAM token (`folder_id` на bucket).

**Ограничение провайдера:** при destroy нужны `depends_on` IAM→cluster (реализовано через `iam_dependency_ids`).

## Security groups

- Нет SSH (22) ingress.
- Kubernetes API (443) только из `k8s_api_allowed_cidrs`; `0.0.0.0/0` запрещён validation.
- По умолчанию список CIDR пуст → публичный API ingress не открыт.
- Node egress `0.0.0.0/0` оставлен для pull образов (документированный компромисс; ужесточение через NAT/private endpoints — позже).

Публичный доступ к inference API — **только** через будущий Ingress/ALB+TLS (не открывается Terraform на 3Б).

## CPU / GPU node groups

| Group | Default | Labels / taints | Notes |
| --- | --- | --- | --- |
| CPU | always on | `workload.credit-scoring/type=cpu` | Serving path; optional `auto_scale` |
| GPU | **off** (`enable_gpu_node_group=false`) | GPU labels + `NoSchedule` taints | Uses schema attrs `resources.gpus`, `gpu_settings`; **NOT_EXECUTED** in cloud |

K8s example (not applied on kind): `k8s/examples/gpu-workload/`.

## Object Storage

- Private via `anonymous_access_flags` (read/list/config_read = false); do **not** use deprecated public ACL
- versioning on
- SSE-KMS optional (default on)
- lifecycle: abort multipart + expire noncurrent

Загрузка моделей в облако на этом этапе **запрещена** (policy). Будущая доставка в Pod:

1. CI кладёт `credit_scoring_nn.onnx` + `preprocessor.joblib` в private bucket.
2. Init/job с SA `ml-reader` (Workload Identity / mounted key — выбрать на этапе deploy) копирует в volume.
3. API монтирует `/app/models` RO — совместимо с контрактом этапа 3А (initContainer pattern сохраняется, источник артефактов меняется с image→bucket).

## Container Registry

Образы:

```text
cr.yandex/<registry-id>/credit-scoring-api@sha256:<digest>
cr.yandex/<registry-id>/credit-scoring-models:<model-version>
```

Предпочтительнее **digest**, не `:latest`. Публикация на 3Б не выполняется.

## Monitoring / logging

- Создаётся Cloud Logging group + master_logging в MK8s.
- `/metrics` API **не** собирается Yandex Monitoring автоматически.
- Нужен будущий Prometheus/VMAgent/агент Monitoring + scrape annotations (уже есть в K8s Service этапа 3А).
- Логи: без финансовых признаков клиента / PII (как в API JSON logging).

## Terraform state

1. Отдельный private bucket на окружение (staging ≠ production key/bucket).
2. S3-compatible backend (`storage.yandexcloud.net`) — `backend.tf.example` + `backend.hcl.example` для `terraform init -backend-config=backend.hcl` (example only; live remote **NOT_EXECUTED**).
3. Отдельный SA только на state bucket (минимум прав); keys via env `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.
4. Versioning + SSE/KMS на state bucket (when creating bucket manually).
5. **Locking:** `use_lockfile` exists in Terraform 1.17 but Yandex compatibility is **NOT_VERIFIED** (not enabled). YDB/dynamodb_table path is deprecated ≥1.11 and not configured. Serialize applies.
6. Не коммитить `*.tfstate`, `*.tfvars`, `backend.hcl`, `.terraform/`.
7. Block 6.1 notes: [`docs/block61_infrastructure_acceptance.md`](block61_infrastructure_acceptance.md).

## Credentials

```powershell
$env:YC_TOKEN = "<iam-token>"   # или YC_SERVICE_ACCOUNT_KEY_FILE
$env:YC_CLOUD_ID = "..."
$env:YC_FOLDER_ID = "..."
```

## Команды проверки (без apply)

```powershell
$tf = ".\tools\terraform.exe"
& $tf -chdir=infra/terraform fmt -recursive -check
& $tf -chdir=infra/terraform/environments/staging init -backend=false
& $tf -chdir=infra/terraform/environments/staging validate
# то же для production
```

`init -backend=false` **скачивает провайдеры из сети** — это не полностью офлайн.

## Будущий deployment (не этап 3Б)

1. `plan` с credentials (отдельное согласование).
2. `apply` staging.
3. Push images by digest; sync artifacts.
4. Адаптировать Kustomize overlay (image digests, cloud LB/Ingress).
5. Smoke `/health/*` `/predict`.
6. Только затем production plan/apply.

## Известные ограничения

- Zonal master (не multi-AZ HA) по умолчанию — стоимость/сложность.
- Node NAT включён для исходящего доступа.
- Точные цены master MK8s нужно перепроверять в калькуляторе/прайс-листе перед apply.
- TFLint/Checkov/Trivy не устанавливались без необходимости.
