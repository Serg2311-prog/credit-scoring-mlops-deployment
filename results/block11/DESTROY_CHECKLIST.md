# DESTROY_CHECKLIST — Block 11.13 (Controlled Cloud Cleanup)

**Branch:** `cloud-deployment` only
**Status:** **STOP GATE DESTROY** — agent prepares commands; **operator executes** destroy/deletes.
**App deploy:** **ABORT_CLOUD_APP** (no cloud app publish/apply).

**Agent MUST NOT run:** `terraform destroy` / `apply`, cloud deletes, bucket wipe, SA deletes, `git commit` / `push`.

---

## 0. Context snapshot (Block 11 facts)

| Topic | Fact |
|-------|------|
| Infra | YC MK8s `cs-exp-k8s` created via Terraform; remote state; Calico; Metrics Server |
| SG migration | 12 standalone `yandex_vpc_security_group_rule` imported; final plan exit 0 (operator) |
| Expected state size | **26** addresses (incl. **12** SG rules) — confirm live with `terraform state list` |
| App images | Built locally (real ONNX); **not** pushed to GHCR; **no** kubectl app apply |
| Trivy | models PASS after remediation; API still FAIL (53 HIGH, FixedVersion empty) |
| Security gates | **Not** weakened; no CVE ignores |
| Distroless follow-up | **Not** continued |
| GHCR | Operator PAT reported with `write:packages`; GitHub API / GHCR token endpoint **HTTP 200**; **Docker Login → denied**. Root cause **not** asserted |

Details: `BLOCK11_ABORT_AND_CLEANUP.md`, `IMAGE_BUILD_REPORT.md`, `application_verification_summary.json`.

---

## 1. Pre-destroy (read-only / local)

```powershell
cd <repo>\infra\terraform\environments\cloud-experiment
git branch --show-current   # must be cloud-deployment

# AWS_* for Object Storage backend (session only; do not commit)
terraform workspace show    # expect default
terraform state list
terraform state list | Measure-Object | Select-Object -ExpandProperty Count
# expect 26 (or document actual count if drift)
```

Confirm **12** rules present:

```powershell
terraform state list | Select-String 'yandex_vpc_security_group_rule'
```

Optional inventory (placeholders only in notes):

```powershell
terraform state show -no-color module.kubernetes.yandex_kubernetes_cluster.this
terraform state show -no-color module.kubernetes.yandex_kubernetes_node_group.cpu
```

- [ ] Branch `cloud-deployment`
- [ ] Workspace `default`
- [ ] State count recorded (target **26**)
- [ ] 12 SG rule addresses listed
- [ ] No production/staging backend key selected

---

## 2. Application / K8s leftovers (if any)

App overlay was **not** applied by agent. Still verify:

```powershell
kubectl config current-context   # yc-cs-exp-k8s
kubectl get ns
kubectl get deploy,svc,ingress,pvc,pv,netpol -A
kubectl get pods -A
```

If any experiment app namespace exists (e.g. `credit-scoring*`):

```powershell
kubectl delete namespace <ns> --wait=true
```

Do **not** reinstall/remove Metrics Server solely for cleanup unless it was installed **outside** Terraform and bills separately (managed add-on usually goes with cluster destroy).

- [ ] No app Deployments/Services/Ingress/PVC from experiment
- [ ] No LoadBalancer Services

---

## 3. STOP GATE DESTROY — operator approval

**Do not proceed until explicit operator approval**, e.g. `APPROVE_TERRAFORM_DESTROY`.

Then:

```powershell
cd <repo>\infra\terraform\environments\cloud-experiment
terraform plan -destroy -input=false -out=destroy.tfplan
terraform show destroy.tfplan
# Review: cluster, node group, VPC/subnet cs-exp-*, SGs + 12 rules, IAM SAs/bindings
# Must NOT target default VPC / default subnets
terraform apply -input=false destroy.tfplan
```

Alternative one-shot (only if plan review done another way):

```powershell
terraform destroy -input=false
```

- [ ] Destroy plan reviewed (26 managed objects incl. 12 rules)
- [ ] No default VPC/subnet in destroy set
- [ ] `terraform apply` destroy succeeded
- [ ] `terraform state list` empty (or only unrelated leftovers documented)

---

## 4. Post-destroy cloud verification (paid surface)

Use folder of the experiment. Filter by `cs-exp` / known labels — **do not delete** pre-experiment **default** VPC/subnets.

```powershell
yc managed-kubernetes cluster list
yc managed-kubernetes node-group list
yc compute instance list
yc compute disk list
yc vpc address list
yc load-balancer network-load-balancer list
yc application-load-balancer load-balancer list
yc vpc network list
yc vpc subnet list
yc vpc security-group list
yc iam service-account list
yc container registry list
yc storage bucket list
```

Expectations:

| Resource | Expectation |
|----------|-------------|
| MK8s clusters / node groups | **none** for experiment |
| Compute instances / disks | **none** for experiment |
| External IPs | **none** leftover (they bill) |
| Networks named `cs-exp-*` | **gone** |
| Subnets `cs-exp-*` | **gone** |
| SGs `cs-exp-*` | **gone** |
| SAs `cs-exp-*-k8s-*` / experiment SAs | **gone** |
| Default VPC / its subnets | **still present** — leave untouched |
| tfstate bucket | **still present** until step 5 |

- [ ] All rows above verified
- [ ] Default VPC/subnets untouched

---

## 5. Remote state bucket (LAST)

Only after step 4 is clean. Bucket name = `bucket` in `backend.hcl` (e.g. documented bootstrap name). Versioning is **on**.

```powershell
$BUCKET = '<TFSTATE_BUCKET_FROM_backend.hcl>'

# List current objects + versions (PowerShell / yc)
yc storage s3api list-object-versions --bucket $BUCKET

# Delete every VersionId and DeleteMarker (loop until empty).
# Example pattern with AWS-compatible API after AWS_* set:
# aws --endpoint-url=https://storage.yandexcloud.net s3api list-object-versions --bucket $BUCKET
# then s3api delete-objects for each VersionId / DeleteMarker
```

Then:

```powershell
yc storage bucket delete --name $BUCKET
yc iam access-key list --service-account-name cs-exp-tfstate-sa
# delete each access key id
yc iam service-account delete --name cs-exp-tfstate-sa
```

- [ ] All object versions + delete markers removed
- [ ] Bucket deleted
- [ ] tfstate SA access keys deleted; SA deleted (if experiment-only)
- [ ] Local `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` cleared from shell

---

## 6. Local / GitHub credential hygiene

```powershell
docker logout ghcr.io
# Revoke temporary GitHub PAT in GitHub → Settings → Developer settings → Tokens
# Clear session leftovers:
Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:GHCR_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
gh auth status   # confirm intended account only
```

Optional local cleanup (not cloud):

```powershell
docker rm -f cs-api-smoke cs-fe-smoke cs-api-secfix 2>$null
# optional: docker rmi credit-scoring-*:cloud-exp-*
```

- [ ] Docker logged out of `ghcr.io`
- [ ] Temporary PAT revoked by operator
- [ ] Shell env credentials cleared

---

## 7. Billing

- [ ] YC billing for experiment window recorded (sanitized)
- [ ] No residual SKUs: MK8s, disks, public IPs, LB
- [ ] Spend within grant expectations

---

## Safety

- Never destroy **production** / **staging** state keys.
- Never delete **default** VPC/subnets that existed before the experiment.
- Never skip version wipe on the state bucket (versioning leaves billable/locked objects).
- Notifications at 100/300/500 ₽ do **not** stop resources.
