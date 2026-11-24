# Ingress E2E via ingress-nginx controller Service port-forward (not frontend SVC).
param(
    [int]$LocalPort = 18080,
    [string]$Namespace = "ingress-nginx",
    [string]$Service = "ingress-nginx-controller",
    [int]$TimeoutSec = 30
)

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:$LocalPort"

Write-Host "==> port-forward $Namespace/$Service -> localhost:$LocalPort"
$pf = Start-Process -PassThru -NoNewWindow -FilePath "kubectl" -ArgumentList @(
    "-n", $Namespace, "port-forward", "svc/$Service", "${LocalPort}:80"
)
Start-Sleep -Seconds 3

try {
    $ui = Invoke-WebRequest "$base/" -UseBasicParsing -TimeoutSec $TimeoutSec
    if ($ui.StatusCode -ne 200 -or ($ui.Content -notmatch "Credit Scoring")) {
        throw "Frontend via Ingress failed"
    }
    Write-Host "OK UI via Ingress"

    $ready = Invoke-RestMethod "$base/health/ready" -TimeoutSec $TimeoutSec
    if ($ready.status -ne "ready") { throw "API /health/ready via Ingress failed" }
    Write-Host "OK API direct path via Ingress"

    $proxy = Invoke-RestMethod "$base/api/health/ready" -TimeoutSec $TimeoutSec
    if ($proxy.status -ne "ready") { throw "Frontend /api proxy via Ingress failed" }
    Write-Host "OK frontend->API proxy via Ingress"

    $body = @{
        LIMIT_BAL = 20000; SEX = 2; EDUCATION = 2; MARRIAGE = 1; AGE = 24
        PAY_0 = 2; PAY_2 = 2; PAY_3 = -1; PAY_4 = -1; PAY_5 = -2; PAY_6 = -2
        BILL_AMT1 = 3913; BILL_AMT2 = 3102; BILL_AMT3 = 689
        BILL_AMT4 = 0; BILL_AMT5 = 0; BILL_AMT6 = 0
        PAY_AMT1 = 0; PAY_AMT2 = 689; PAY_AMT3 = 0; PAY_AMT4 = 0; PAY_AMT5 = 0; PAY_AMT6 = 0
    } | ConvertTo-Json
    $pred = Invoke-RestMethod "$base/api/predict" -Method Post -Body $body -ContentType "application/json" -TimeoutSec $TimeoutSec
    if ($null -eq $pred.probability_default) { throw "predict missing probability" }
    Write-Host "OK scoring via Ingress proba=$($pred.probability_default)"

    try {
        Invoke-WebRequest "$base/api/predict" -Method Post -Body '{"LIMIT_BAL":-1}' -ContentType "application/json" -TimeoutSec $TimeoutSec | Out-Null
        throw "expected 422 for invalid payload"
    } catch {
        $code = [int]$_.Exception.Response.StatusCode
        if ($code -ne 422) { throw "expected HTTP 422, got $code" }
        Write-Host "OK invalid payload -> HTTP 422"
    }
    Write-Host "INGRESS_E2E_PASS"
} finally {
    if ($pf -and -not $pf.HasExited) {
        Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue
    }
}
