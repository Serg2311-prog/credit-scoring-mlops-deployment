# Terraform — Yandex Cloud (Stage 3B)

IaC for future Credit Scoring deployment. **No `terraform apply` in stage 3B.**

## Layout

```text
infra/terraform/
  modules/
    network/      # VPC, subnets, security groups
    iam/          # least-privilege service accounts
    kubernetes/   # Managed Kubernetes + CPU node group
    registry/     # Container Registry
    storage/      # private Object Storage + optional KMS
    monitoring/   # Cloud Logging group (+ metrics notes)
  environments/
    staging/
    production/
```

## Credentials (never commit)

```powershell
$env:YC_TOKEN = "<iam-token>"          # or YC_SERVICE_ACCOUNT_KEY_FILE
$env:YC_CLOUD_ID = "<cloud-id>"
$env:YC_FOLDER_ID = "<folder-id>"
```

Provider also accepts `cloud_id` / `folder_id` via `terraform.tfvars` (gitignored).

## Static checks (allowed)

```powershell
$tf = ".\tools\terraform.exe"   # or terraform on PATH
& $tf -chdir=infra/terraform fmt -recursive -check

# per environment
& $tf -chdir=infra/terraform/environments/staging init -backend=false
& $tf -chdir=infra/terraform/environments/staging validate

& $tf -chdir=infra/terraform/environments/production init -backend=false
& $tf -chdir=infra/terraform/environments/production validate
```

## Forbidden without explicit approval

- `terraform apply` / `terraform destroy`
- uploading images/models
- creating paid cloud resources

## Future deploy (documentation only)

1. Create separate folders for staging/production.
2. Create private state buckets; copy `backend.tf.example` → `backend.tf`.
3. Fill `terraform.tfvars` from example.
4. `terraform plan` (separate approval) → `apply` (separate approval).
5. Push images by digest; sync artifacts to private bucket.
6. Deploy Kustomize overlay adapted for cloud (future stage).
