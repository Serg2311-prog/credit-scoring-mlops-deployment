# Terraform — Yandex Cloud (Этап 2 / Block 6)

IaC for Credit Scoring staging/production/`cloud-experiment`.
**Default path:** No `terraform apply` for staging/production in CI or routine workflows.
**Block 11 exception:** `cloud-experiment` was applied once in Yandex Cloud (live Remote State), then **destroyed** (operator). State bucket and access keys removed. Further `apply`/`destroy` only with explicit approval (grant burn).

## Layout

```text
infra/terraform/
  modules/
    network/      # VPC, subnets, security groups
    iam/          # least-privilege service accounts
    kubernetes/   # Managed Kubernetes + CPU NG + optional GPU NG
    registry/     # Container Registry
    storage/      # private Object Storage + optional KMS
    monitoring/   # Cloud Logging group (+ metrics notes)
  environments/
    staging/
    production/
    cloud-experiment/   # Block 11.5 short grant-funded experiment (quota-locked)
```

## CPU / GPU

- CPU node group: always defined (serving).
- GPU node group: `enable_gpu_node_group=false` by default (cost control).
- Do not enable GPU without budget approval. Cloud GPU create = **NOT_EXECUTED** here.

## Remote state

See `environments/*/backend.tf.example`. **cloud-experiment** used live Object Storage remote state (Block 11); bucket **deleted** after destroy.
Locking (`use_lockfile`) still **NOT_VERIFIED** on Yandex. Bootstrap notes (historical): `results/block11/REMOTE_STATE_BOOTSTRAP.md`.

## Credentials (never commit)

```powershell
$env:YC_TOKEN = "<iam-token>"          # or YC_SERVICE_ACCOUNT_KEY_FILE
$env:YC_CLOUD_ID = "<cloud-id>"
$env:YC_FOLDER_ID = "<folder-id>"
```

Provider also accepts `cloud_id` / `folder_id` via `terraform.tfvars` (gitignored).

## Static checks (allowed)

```powershell
terraform -chdir=infra/terraform fmt -recursive -check
terraform -chdir=infra/terraform/environments/staging init -backend=false
terraform -chdir=infra/terraform/environments/staging validate
terraform -chdir=infra/terraform/environments/production init -backend=false
terraform -chdir=infra/terraform/environments/production validate
terraform -chdir=infra/terraform/environments/cloud-experiment init -backend=false
terraform -chdir=infra/terraform/environments/cloud-experiment validate
terraform -chdir=infra/terraform/modules/kubernetes test
```

`cloud-experiment` locks worker size to confirmed quotas (4 vCPU / 16 GB / 64 GiB), forces GPU/autoscaling off, sets `deploy_policy.max_expansion=0`, master min preset `s-c2-m8` (floor, not max), and disables ml-reader/registry-pusher SAs.
Network SG rules are **rule-resources only** (Block 11.9.1) — do not reintroduce inline+separate dual management. Migration completed in experiment; plan/history: `results/block11/STATE_MIGRATION_PLAN.md`.

## Forbidden without explicit approval

- `terraform apply` / `terraform destroy`
- uploading images/models
- creating paid cloud resources
- enabling `enable_gpu_node_group=true` without budget note

## Docs

- `docs/stage2_infrastructure_completion_report.md`
- `docs/terraform_infrastructure.md`
