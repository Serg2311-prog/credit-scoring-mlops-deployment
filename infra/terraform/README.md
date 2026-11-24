# Terraform — Yandex Cloud (Этап 2 / Block 6)

IaC for Credit Scoring staging/production. **No `terraform apply` without explicit approval.**

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
```

## CPU / GPU

- CPU node group: always defined (serving).
- GPU node group: `enable_gpu_node_group=false` by default (cost control).
- Do not enable GPU without budget approval. Cloud GPU create = **NOT_EXECUTED** here.

## Remote state

See `environments/*/backend.tf.example`. Example only — live remote backend **NOT_EXECUTED**.

Locking on Yandex Object Storage has no DynamoDB-style lock; serialize applies.

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
```

## Forbidden without explicit approval

- `terraform apply` / `terraform destroy`
- uploading images/models
- creating paid cloud resources
- enabling `enable_gpu_node_group=true` without budget note

## Docs

- `docs/stage2_infrastructure_completion_report.md`
- `docs/terraform_infrastructure.md`
