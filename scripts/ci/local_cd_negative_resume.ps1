# Resume Block 5 negative rollout + recovery after a partial local_cd_verify run.
$ErrorActionPreference = "Continue"
$Context = "kind-credit-scoring"
$ClusterName = "credit-scoring"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$OutDir = Join-Path $Root "artifacts\ci\local_cd"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$ApiImage2 = "credit-scoring-api:cd-20261124110017-r2"
$ModelsImage2 = "credit-scoring-models:cd-20261124110017-r2"
$FrontendImage2 = "credit-scoring-frontend:cd-20261124110017-r2"
$BadImage = "credit-scoring-api:cd-bad-resume"

$badDir = Join-Path $OutDir "badimage"
New-Item -ItemType Directory -Force -Path $badDir | Out-Null
$dockerFile = @(
    "FROM $ApiImage2"
    'ENTRYPOINT ["sh", "-c", "echo broken-on-purpose; exit 1"]'
) -join "`n"
[IO.File]::WriteAllText((Join-Path $badDir "Dockerfile"), $dockerFile)

Write-Host "==> Build broken image"
docker build -t $BadImage $badDir
if ($LASTEXITCODE -ne 0) { throw "bad image build failed" }
kind load docker-image $BadImage --name $ClusterName
if ($LASTEXITCODE -ne 0) { throw "kind load bad failed" }

Write-Host "==> Apply broken image"
& $Py scripts/ci/render_cd_images.py `
    --overlay (Join-Path $Root "k8s\overlays\cd-demo-staging") `
    --api-image $BadImage `
    --models-image $ModelsImage2 `
    --frontend-image $FrontendImage2 `
    --output (Join-Path $OutDir "staging_bad.yaml")
kubectl --context $Context apply -f (Join-Path $OutDir "staging_bad.yaml")
Write-Host "==> Expect rollout failure"
kubectl --context $Context -n credit-scoring-cd-staging rollout status deploy/credit-scoring-api --timeout=60s 2>&1 |
    Tee-Object (Join-Path $OutDir "negative_rollout.txt")
$neg = $LASTEXITCODE
Write-Host "negative exit=$neg"
if ($neg -eq 0) { throw "expected negative rollout failure" }

Write-Host "==> Recover with good images"
$stagingYaml2 = Join-Path $OutDir "staging_r2.yaml"
if (-not (Test-Path $stagingYaml2)) {
    & $Py scripts/ci/render_cd_images.py `
        --overlay (Join-Path $Root "k8s\overlays\cd-demo-staging") `
        --api-image $ApiImage2 `
        --models-image $ModelsImage2 `
        --frontend-image $FrontendImage2 `
        --output $stagingYaml2
}
kubectl --context $Context apply -f $stagingYaml2
kubectl --context $Context -n credit-scoring-cd-staging rollout status deploy/credit-scoring-api --timeout=180s
if ($LASTEXITCODE -ne 0) { throw "recovery rollout failed" }

$pf = Start-Process -FilePath "kubectl" -ArgumentList @(
    "--context", $Context, "-n", "ingress-nginx", "port-forward", "svc/ingress-nginx-controller", "18080:80"
) -PassThru -WindowStyle Hidden -RedirectStandardError (Join-Path $OutDir "pf2_err.txt") -RedirectStandardOutput (Join-Path $OutDir "pf2_out.txt")
Start-Sleep -Seconds 3
try {
    & $Py scripts/ci/smoke_http.py --base-url "http://127.0.0.1:18080" --host "cd-staging.local" `
        --expect-model-version "mlp-onnx-fp32-v1" `
        --output (Join-Path $OutDir "smoke_staging_recovered.json")
    if ($LASTEXITCODE -ne 0) { throw "recovery smoke failed" }
}
finally {
    if ($pf -and -not $pf.HasExited) { Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue }
}

$summary = @{
    status          = "VERIFIED_LOCAL"
    negative_exit   = $neg
    recovered       = $true
    note            = "Negative+recover resumed after PowerShell docker stderr abort"
}
($summary | ConvertTo-Json) | Set-Content (Join-Path $OutDir "negative_resume_summary.json") -Encoding utf8
Write-Host "NEGATIVE+RECOVER PASS" -ForegroundColor Green
