# Smoke-test API via kubectl port-forward.
param(
    [int]$LocalPort = 8000,
    [int]$WaitSeconds = 90
)

. "$PSScriptRoot\k8s_common.ps1"

Write-Step "Checking prerequisites"
Assert-Command kubectl
$kindExe = Get-KindExe
Set-KindKubeContext -KindExe $kindExe

Write-Step "Waiting until Deployment is Available"
$deployRef = "deployment/{0}" -f $script:DeploymentName
$timeoutFlag = "--timeout={0}s" -f $WaitSeconds
kubectl -n $script:Namespace wait --for=condition=Available $deployRef $timeoutFlag
Assert-LastExitCode "kubectl wait Available"

$pf = $null
try {
    Write-Step ("Starting port-forward on localhost:{0}" -f $LocalPort)
    $pfArgs = @(
        "-n", $script:Namespace,
        "port-forward",
        ("svc/{0}" -f $script:ServiceName),
        ("{0}:8000" -f $LocalPort)
    )
    $pf = Start-Process -FilePath "kubectl" -ArgumentList $pfArgs `
        -RedirectStandardOutput (Join-Path $env:TEMP "k8s-pf-out.log") `
        -RedirectStandardError (Join-Path $env:TEMP "k8s-pf-err.log") `
        -PassThru -WindowStyle Hidden

    $base = "http://127.0.0.1:{0}" -f $LocalPort
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $live = Invoke-RestMethod -Uri ($base + "/health/live") -Method Get -TimeoutSec 2
            if ($live.status -eq "ok") {
                $ready = $true
                break
            }
        }
        catch {
            # port-forward still starting
        }
    }
    if (-not $ready) {
        throw "port-forward /health/live did not become reachable"
    }

    Write-Step "GET /health/live"
    $live = Invoke-RestMethod -Uri ($base + "/health/live") -Method Get
    Write-Host ($live | ConvertTo-Json -Compress)

    Write-Step "GET /health/ready"
    $rdy = Invoke-RestMethod -Uri ($base + "/health/ready") -Method Get
    Write-Host ($rdy | ConvertTo-Json -Compress)
    if ($rdy.status -ne "ready") {
        throw "readiness not ready"
    }

    Write-Step "GET /model/info"
    $info = Invoke-RestMethod -Uri ($base + "/model/info") -Method Get
    Write-Host ($info | ConvertTo-Json -Compress)

    Write-Step "GET /metrics"
    $metrics = Invoke-WebRequest -Uri ($base + "/metrics") -UseBasicParsing
    if ($metrics.StatusCode -ne 200) {
        throw "/metrics failed"
    }
    if ($metrics.Content -notmatch "model_ready") {
        throw "/metrics missing model_ready"
    }
    Write-Host ("metrics bytes={0}" -f $metrics.Content.Length)

    $sample = @{
        LIMIT_BAL = 20000
        SEX       = 2
        EDUCATION = 2
        MARRIAGE  = 1
        AGE       = 24
        PAY_0     = 2
        PAY_2     = 2
        PAY_3     = -1
        PAY_4     = -1
        PAY_5     = -2
        PAY_6     = -2
        BILL_AMT1 = 3913
        BILL_AMT2 = 3102
        BILL_AMT3 = 689
        BILL_AMT4 = 0
        BILL_AMT5 = 0
        BILL_AMT6 = 0
        PAY_AMT1  = 0
        PAY_AMT2  = 689
        PAY_AMT3  = 0
        PAY_AMT4  = 0
        PAY_AMT5  = 0
        PAY_AMT6  = 0
    }

    Write-Step "POST /predict"
    $pred = Invoke-RestMethod -Uri ($base + "/predict") -Method Post `
        -ContentType "application/json" `
        -Body ($sample | ConvertTo-Json)
    Write-Host ($pred | ConvertTo-Json -Compress)
    if ($null -eq $pred.probability_default) {
        throw "predict missing probability_default"
    }

    Write-Step "POST /predict/batch"
    $batchBody = @{ items = @($sample, $sample) } | ConvertTo-Json -Depth 5
    $batch = Invoke-RestMethod -Uri ($base + "/predict/batch") -Method Post `
        -ContentType "application/json" `
        -Body $batchBody
    Write-Host ($batch | ConvertTo-Json -Compress)
    if ($batch.batch_size -ne 2) {
        throw "unexpected batch_size"
    }

    Write-Host "OK: k8s smoke passed"
}
finally {
    if ($null -ne $pf -and -not $pf.HasExited) {
        Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue
    }
}
