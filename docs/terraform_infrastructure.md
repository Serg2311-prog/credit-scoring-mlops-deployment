# Terraform Infrastructure — Yandex Cloud (Stage 3B)

**Статус:** код и документация подготовлены.
**Факт:** облачные ресурсы **не создавались**. `terraform apply` / `destroy` **не выполнялись**.

## Архитектура модулей

```text
environments/{staging|production}
    → module.network
    → module.iam
    → module.monitoring
    → module.registry
    → module.storage
    → module.kubernetes  (depends on network + iam + monitoring log group)
```

| Модуль | Ресурсы | Назначение |
| --- | --- | --- |
| `network` | `yandex_vpc_network`, `yandex_vpc_subnet`, SG + rule | VPC, CIDR, master/nodes SG |
| `iam` | SA + `folder_iam_member` | least privilege |
| `kubernetes` | `yandex_kubernetes_cluster`, `yandex_kubernetes_node_group` | MK8s CPU-only |
| `registry` | `yandex_container_registry` | API + models images |
| `storage` | `yandex_storage_bucket`, optional `yandex_kms_symmetric_key` | private ML artifacts |
| `monitoring` | `yandex_logging_group` | master/app logs retention |

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

## Object Storage

- `acl = private`
- anonymous read/list/config_read = false
- versioning on
- SSE-KMS optional (default on)
- lifecycle: abort multipart + expire noncurrent

Загрузка моделей на 3Б **запрещена**. Будущая доставка в Pod:

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

1. Отдельный private bucket на окружение.
2. S3-compatible backend (`storage.yandexcloud.net`) — см. `backend.tf.example`.
3. Отдельный SA только на state bucket (минимум прав).
4. Versioning + SSE на state bucket.
5. State lock: стандартный S3 lock Yandex/Terraform — проверить актуальные ограничения backend перед apply.
6. Не коммитить `*.tfstate`, `*.tfvars`, `.terraform/`.

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
