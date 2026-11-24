# Block 5 local CD verification on existing kind cluster (NOT cloud production).
# Isolated namespaces: credit-scoring-cd-staging, credit-scoring-cd-prod.
# Does not delete kind cluster or user volumes.
param(
    [string]$ClusterName = "credit-scoring",
    [string]$Context = "kind-credit-scoring",
    [switch]$SkipBuild,
    [switch]$SkipNegative,
    [int]$RolloutTimeoutSec = 180
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
$OutDir = Join-Path $Root "artifacts\ci\local_cd"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Tag = "cd-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
$ApiImage = "credit-scoring-api:$Tag"
$ModelsImage = "credit-scoring-models:$Tag"
$FrontendImage = "credit-scoring-frontend:$Tag"
$BadImage = "credit-scoring-api:cd-bad-$Tag"

function Write-Step([string]$Msg) { Write-Host "==> $Msg" -ForegroundColor Cyan }
function Fail([string]$Msg) { Write-Host "FAIL: $Msg" -ForegroundColor Red; throw $Msg }

function Invoke-Kubectl([string[]]$Args) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & kubectl --context $Context @Args
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($null -ne $code -and $code -ne 0) {
        Fail ("kubectl " + ($Args -join " ") + " exit=$code")
    }
}

function Get-IngressBase {
    # Port-forward ingress-nginx controller.
    return "http://127.0.0.1:18080"
}

Write-Step "0) Resource / cluster check"
docker info | Out-Null
kind get clusters | Out-String | Write-Host
$nodes = kubectl --context $Context get nodes -o wide 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Fail "kind context $Context unavailable: $nodes" }
Write-Host $nodes
kubectl --context $Context get pods -A | Out-String | Tee-Object (Join-Path $OutDir "pods_before.txt") | Out-Null
$ing = kubectl --context $Context -n ingress-nginx get pods 2>&1 | Out-String
if ($ing -notmatch "ingress-nginx-controller") {
    Fail "ingress-nginx not found — install controller before CD verify"
}

Write-Step "1) CI gate (local skip allowed)"
& $Py scripts/ci/check_required_ci.py --sha "local-cd-$Tag" --allow-local-skip --output (Join-Path $OutDir "ci_gate.json")
if ($LASTEXITCODE -ne 0) { Fail "ci gate failed" }

Write-Step "2) Use existing models/ artifacts (no regenerate — keep production hashes)"
# Do NOT run generate_synthetic_artifacts --force here; it would mutate production ONNX.
$modelVersion = "mlp-onnx-fp32-v1"
if (-not (Test-Path (Join-Path $Root "models\credit_scoring_nn.onnx"))) {
    Fail "models/credit_scoring_nn.onnx missing"
}

if (-not $SkipBuild) {
    Write-Step "3) Build immutable images tag=$Tag"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker build -f docker/Dockerfile.api -t $ApiImage . 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = $prev; Fail "api build" }
    docker build -f docker/Dockerfile.models -t $ModelsImage . 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = $prev; Fail "models build" }
    docker build -f docker/Dockerfile.frontend -t $FrontendImage . 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = $prev; Fail "frontend build" }
    Write-Step "kind load images"
    kind load docker-image $ApiImage $ModelsImage $FrontendImage --name $ClusterName 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = $prev; Fail "kind load" }
    $ErrorActionPreference = $prev
}

Write-Step "4) Render + deploy staging demo namespace"
$stagingYaml = Join-Path $OutDir "staging.yaml"
& $Py scripts/ci/render_cd_images.py `
    --overlay (Join-Path $Root "k8s\overlays\cd-demo-staging") `
    --api-image $ApiImage `
    --models-image $ModelsImage `
    --frontend-image $FrontendImage `
    --output $stagingYaml
if ($LASTEXITCODE -ne 0) { Fail "render staging" }
Invoke-Kubectl @("apply", "-f", $stagingYaml)
Invoke-Kubectl @("-n", "credit-scoring-cd-staging", "rollout", "status", "deploy/credit-scoring-api", "--timeout=${RolloutTimeoutSec}s")
Invoke-Kubectl @("-n", "credit-scoring-cd-staging", "rollout", "status", "deploy/credit-scoring-frontend", "--timeout=${RolloutTimeoutSec}s")

Write-Step "5) Start ingress port-forward + staging smoke"
$pf = Start-Process -FilePath "kubectl" -ArgumentList @(
    "--context", $Context, "-n", "ingress-nginx", "port-forward", "svc/ingress-nginx-controller", "18080:80"
) -PassThru -WindowStyle Hidden -RedirectStandardError (Join-Path $OutDir "pf_err.txt") -RedirectStandardOutput (Join-Path $OutDir "pf_out.txt")
Start-Sleep -Seconds 3
try {
    & $Py scripts/ci/smoke_http.py --base-url (Get-IngressBase) --host "cd-staging.local" `
        --expect-model-version $modelVersion `
        --output (Join-Path $OutDir "smoke_staging.json")
    if ($LASTEXITCODE -ne 0) { Fail "staging smoke failed" }

    Write-Step "6) Promote SAME images to production-demo namespace"
    $prodYaml = Join-Path $OutDir "prod.yaml"
    & $Py scripts/ci/render_cd_images.py `
        --overlay (Join-Path $Root "k8s\overlays\cd-demo-production") `
        --api-image $ApiImage `
        --models-image $ModelsImage `
        --frontend-image $FrontendImage `
        --output $prodYaml
    if ($LASTEXITCODE -ne 0) { Fail "render prod" }
    Invoke-Kubectl @("apply", "-f", $prodYaml)
    Invoke-Kubectl @("-n", "credit-scoring-cd-prod", "rollout", "status", "deploy/credit-scoring-api", "--timeout=${RolloutTimeoutSec}s")
    Invoke-Kubectl @("-n", "credit-scoring-cd-prod", "rollout", "status", "deploy/credit-scoring-frontend", "--timeout=${RolloutTimeoutSec}s")
    & $Py scripts/ci/smoke_http.py --base-url (Get-IngressBase) --host "cd-prod.local" `
        --expect-model-version $modelVersion `
        --output (Join-Path $OutDir "smoke_prod.json")
    if ($LASTEXITCODE -ne 0) { Fail "prod-demo smoke failed" }

    Write-Step "7) Redeploy new immutable version to staging"
    $Tag2 = $Tag + "-r2"
    $ApiImage2 = "credit-scoring-api:$Tag2"
    $ModelsImage2 = "credit-scoring-models:$Tag2"
    $FrontendImage2 = "credit-scoring-frontend:$Tag2"
    docker tag $ApiImage $ApiImage2
    docker tag $ModelsImage $ModelsImage2
    docker tag $FrontendImage $FrontendImage2
    kind load docker-image $ApiImage2 $ModelsImage2 $FrontendImage2 --name $ClusterName
    if ($LASTEXITCODE -ne 0) { Fail "kind load r2" }
    $stagingYaml2 = Join-Path $OutDir "staging_r2.yaml"
    & $Py scripts/ci/render_cd_images.py `
        --overlay (Join-Path $Root "k8s\overlays\cd-demo-staging") `
        --api-image $ApiImage2 `
        --models-image $ModelsImage2 `
        --frontend-image $FrontendImage2 `
        --output $stagingYaml2
    Invoke-Kubectl @("apply", "-f", $stagingYaml2)
    Invoke-Kubectl @("-n", "credit-scoring-cd-staging", "rollout", "status", "deploy/credit-scoring-api", "--timeout=${RolloutTimeoutSec}s")
    & $Py scripts/ci/smoke_http.py --base-url (Get-IngressBase) --host "cd-staging.local" `
        --expect-model-version $modelVersion `
        --output (Join-Path $OutDir "smoke_staging_r2.json")
    if ($LASTEXITCODE -ne 0) { Fail "staging r2 smoke failed" }

    if (-not $SkipNegative) {
        Write-Step "8) Negative scenario: broken image → rollout failure → recover"
        # Create a deliberately broken image from the known-good API image.
        $badDir = Join-Path $OutDir "badimage"
        New-Item -ItemType Directory -Force -Path $badDir | Out-Null
        @"
FROM $ApiImage2
ENTRYPOINT ["sh", "-c", "echo broken-on-purpose; exit 1"]
"@ | Set-Content -Path (Join-Path $badDir "Dockerfile") -Encoding ascii
        $prevDocker = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        docker build -t $BadImage $badDir 2>&1 | Out-Host
        $badBuild = $LASTEXITCODE
        $ErrorActionPreference = $prevDocker
        if ($badBuild -ne 0) { Fail "bad image build" }
        $ErrorActionPreference = "Continue"
        kind load docker-image $BadImage --name $ClusterName 2>&1 | Out-Host
        $loadCode = $LASTEXITCODE
        $ErrorActionPreference = $prevDocker
        if ($loadCode -ne 0) { Fail "kind load bad image" }
        $badYaml = Join-Path $OutDir "staging_bad.yaml"
        & $Py scripts/ci/render_cd_images.py `
            --overlay (Join-Path $Root "k8s\overlays\cd-demo-staging") `
            --api-image $BadImage `
            --models-image $ModelsImage2 `
            --frontend-image $FrontendImage2 `
            --output $badYaml
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        kubectl --context $Context apply -f $badYaml 2>&1 | Out-Null
        kubectl --context $Context -n credit-scoring-cd-staging rollout status deploy/credit-scoring-api --timeout=60s 2>&1 |
            Tee-Object (Join-Path $OutDir "negative_rollout.txt") | Out-Null
        $negCode = $LASTEXITCODE
        $ErrorActionPreference = $prev
        if ($negCode -eq 0) {
            Fail "expected negative rollout to fail, but it succeeded"
        }
        Write-Host "Negative rollout failed as expected (exit=$negCode)"
        Write-Step "9) Recover with known-good images"
        Invoke-Kubectl @("apply", "-f", $stagingYaml2)
        Invoke-Kubectl @("-n", "credit-scoring-cd-staging", "rollout", "status", "deploy/credit-scoring-api", "--timeout=${RolloutTimeoutSec}s")
        & $Py scripts/ci/smoke_http.py --base-url (Get-IngressBase) --host "cd-staging.local" `
            --expect-model-version $modelVersion `
            --output (Join-Path $OutDir "smoke_staging_recovered.json")
        if ($LASTEXITCODE -ne 0) { Fail "recovery smoke failed" }
    }
}
finally {
    if ($pf -and -not $pf.HasExited) {
        Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue
    }
}

$summary = [ordered]@{
    status           = "VERIFIED_LOCAL"
    not_cloud        = $true
    tag              = $Tag
    api_image        = $ApiImage
    models_image     = $ModelsImage
    frontend_image   = $FrontendImage
    staging_ns       = "credit-scoring-cd-staging"
    prod_demo_ns     = "credit-scoring-cd-prod"
    model_version    = $modelVersion
    negative_tested  = (-not $SkipNegative)
}
($summary | ConvertTo-Json -Depth 5) | Set-Content (Join-Path $OutDir "summary.json") -Encoding utf8
Write-Host "LOCAL CD VERIFY PASS — $OutDir\summary.json" -ForegroundColor Green
exit 0
