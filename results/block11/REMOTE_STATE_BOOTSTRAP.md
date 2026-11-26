# Remote State Bootstrap — Yandex Object Storage (Block 11.7.1)

**Status at document creation (11.7.1):** instruction pack for the operator — agent marked **NOT_EXECUTED** (no bucket/SA/keys/policy created *by the agent at that step*).
**Later factual outcome:** operator completed remote-state bootstrap and used live Object Storage state for `cloud-experiment`; infrastructure was later destroyed and the state bucket removed. See [`FINAL_CLOUD_EXPERIMENT_REPORT.md`](FINAL_CLOUD_EXPERIMENT_REPORT.md), [`FINAL_CLEANUP_REPORT.md`](FINAL_CLEANUP_REPORT.md), [`CLOUD_RUNTIME_VERIFICATION.md`](CLOUD_RUNTIME_VERIFICATION.md).
**Environment key (historical):** `credit-scoring/cloud-experiment/terraform.tfstate`
**Do not** grant the tfstate SA folder/cloud-wide roles (`storage.admin`, `editor`, `admin`).

Official references:
- [Bucket policy concepts](https://yandex.cloud/en/docs/storage/concepts/policy)
- [Manage bucket policy](https://yandex.cloud/en/docs/storage/operations/buckets/policy)
- [Policy actions](https://yandex.cloud/en/docs/storage/s3/api-ref/policy/actions)
- CLI: `yc storage bucket create|update --versioning|--policy-from-file`
  (`yc storage bucket add-access-binding` is **unavailable** — use Bucket Policy)

## 0. Placeholders (replace locally; never commit)

| Placeholder | Meaning |
|-------------|---------|
| `<BUCKET>` | Globally unique private bucket name |
| `<FOLDER_ID>` | Experiment folder ID |
| `<TFSTATE_SA_NAME>` | e.g. `cs-exp-tfstate-sa` |
| `<TFSTATE_SA_ID>` | Service account ID (`aje…`) after create |
| `<STATE_PREFIX>` | `credit-scoring/cloud-experiment` |

## 1. Create private bucket + versioning

```powershell
# Run only after explicit operator approval. Do NOT echo secrets.
yc storage bucket create `
  --name <BUCKET> `
  --folder-id <FOLDER_ID> `
  --default-storage-class standard `
  --max-size 1073741824 `
  --public-read false `
  --public-list false `
  --public-config-read false

yc storage bucket update `
  --name <BUCKET> `
  --versioning versioning-enabled
```

Confirm private access / versioning in console or:

```powershell
yc storage bucket get --name <BUCKET>
```

## 2. Dedicated service account (no folder roles)

```powershell
yc iam service-account create `
  --name <TFSTATE_SA_NAME> `
  --folder-id <FOLDER_ID> `
  --description "Terraform remote state for cloud-experiment only"

# Capture ID (do not paste into Git):
yc iam service-account get <TFSTATE_SA_NAME> --folder-id <FOLDER_ID>
```

**Do not** run `yc resource-manager folder add-access-binding` for this SA.

## 3. Bucket Policy (least privilege)

Create a local file `tfstate-bucket-policy.json` (gitignored path recommended, e.g. under a local secrets dir):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TfstateListBucket",
      "Effect": "Allow",
      "Principal": {
        "CanonicalUser": "<TFSTATE_SA_ID>"
      },
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::<BUCKET>"
      ],
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "<STATE_PREFIX>/*",
            "<STATE_PREFIX>"
          ]
        }
      }
    },
    {
      "Sid": "TfstateObjectRW",
      "Effect": "Allow",
      "Principal": {
        "CanonicalUser": "<TFSTATE_SA_ID>"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetObjectVersion",
        "s3:DeleteObjectVersion"
      ],
      "Resource": [
        "arn:aws:s3:::<BUCKET>/<STATE_PREFIX>/*"
      ]
    }
  ]
}
```

Apply:

```powershell
yc storage bucket update `
  --name <BUCKET> `
  --policy-from-file .\tfstate-bucket-policy.json
```

Notes:
- `Principal.CanonicalUser` = service account ID (YC Object Storage subject id).
- Actions cover Terraform S3 backend read/write/delete + versioned recovery.
- Scope objects to the experiment prefix only.
- If `ListBucket` + `s3:prefix` Condition is rejected by the API in practice, fall back to `s3:ListBucket` on the bucket ARN **without** broadening object `Resource` beyond `<STATE_PREFIX>/*`, and keep folder IAM empty.

## 4. Static access keys (env only)

```powershell
yc iam access-key create `
  --service-account-name <TFSTATE_SA_NAME> `
  --folder-id <FOLDER_ID> `
  --description "tfstate cloud-experiment"
```

Export (session only; never `-backend-config=access_key=...` on CLI — history leak):

```powershell
$env:AWS_ACCESS_KEY_ID     = "<key-id>"
$env:AWS_SECRET_ACCESS_KEY = "<secret>"
# Do not Write-Output / Set-Content these values into the repo.
```

Store the secret in an operator password manager; delete local copies of the create JSON after export.

## 5. Terraform backend wiring

Copy examples (gitignored targets):

```powershell
cd infra/terraform/environments/cloud-experiment
Copy-Item backend.tf.example backend.tf   # if using empty backend "s3" {}
Copy-Item backend.hcl.example backend.hcl
# Edit backend.hcl: bucket=<BUCKET>, key=credit-scoring/cloud-experiment/terraform.tfstate
```

`backend.hcl.example` already sets Yandex S3 endpoint skips.
`use_lockfile` remains **disabled** (Yandex compatibility **NOT_VERIFIED**). Serialize operators.

```powershell
terraform init -backend-config=backend.hcl
terraform plan
```

## 6. State recovery

1. Bucket versioning must be ON before first `init`.
2. On corruption: restore previous object version of the state key in console/CLI, then `terraform init` + `terraform plan`.
3. Keep an encrypted local backup of `terraform.tfstate` after successful apply (laptop only; gitignored).

## 7. Teardown order (after infra destroy)

1. `terraform destroy` for cloud-experiment (approved).
2. Verify no Compute/MK8s/LB leftovers.
3. Empty bucket including noncurrent versions.
4. `yc storage bucket delete --name <BUCKET>`
5. Delete access keys; delete tfstate SA.
6. Clear `$env:AWS_ACCESS_KEY_ID` / `$env:AWS_SECRET_ACCESS_KEY` from the shell.

## Exact bootstrap command sequence (copy/paste after approval)

```powershell
# 1–3: bucket + SA + policy (no folder IAM)
# 4: access-key create → export AWS_* in current session only
# 5:
cd infra/terraform/environments/cloud-experiment
# prepare backend.tf + backend.hcl (gitignored)
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
# STOP for plan review — apply only with separate approval
```
