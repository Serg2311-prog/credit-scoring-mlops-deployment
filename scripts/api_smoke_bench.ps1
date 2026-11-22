# Smoke + light API performance test (PowerShell)
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$Warmup = 5,
    [int]$Timed = 30
)

$ErrorActionPreference = "Stop"
$sample = @{
    LIMIT_BAL = 20000.0; SEX = 2; EDUCATION = 2; MARRIAGE = 1; AGE = 24
    PAY_0 = 2; PAY_2 = 2; PAY_3 = -1; PAY_4 = -1; PAY_5 = -2; PAY_6 = -2
    BILL_AMT1 = 3913.0; BILL_AMT2 = 3102.0; BILL_AMT3 = 689.0
    BILL_AMT4 = 0.0; BILL_AMT5 = 0.0; BILL_AMT6 = 0.0
    PAY_AMT1 = 0.0; PAY_AMT2 = 689.0; PAY_AMT3 = 0.0
    PAY_AMT4 = 0.0; PAY_AMT5 = 0.0; PAY_AMT6 = 0.0
}

function Invoke-JsonPost($Url, $Body) {
    return Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 6)
}

Write-Host "GET $BaseUrl/health/live"
Invoke-RestMethod "$BaseUrl/health/live" | ConvertTo-Json -Compress
Write-Host "GET $BaseUrl/health/ready"
Invoke-RestMethod "$BaseUrl/health/ready" | ConvertTo-Json -Compress
Write-Host "GET $BaseUrl/model/info"
Invoke-RestMethod "$BaseUrl/model/info" | ConvertTo-Json -Compress
Write-Host "POST /predict"
Invoke-JsonPost "$BaseUrl/predict" $sample | ConvertTo-Json -Compress

$batchSizes = @(1, 16, 64, 256)
$report = @()
foreach ($bs in $batchSizes) {
    $items = @()
    for ($i = 0; $i -lt $bs; $i++) { $items += $sample }
    $body = @{ items = $items }
    for ($i = 0; $i -lt $Warmup; $i++) {
        Invoke-JsonPost "$BaseUrl/predict/batch" $body | Out-Null
    }
    $lat = @()
    $sw = [System.Diagnostics.Stopwatch]::new()
    for ($i = 0; $i -lt $Timed; $i++) {
        $sw.Restart()
        Invoke-JsonPost "$BaseUrl/predict/batch" $body | Out-Null
        $sw.Stop()
        $lat += $sw.Elapsed.TotalMilliseconds
    }
    $sorted = $lat | Sort-Object
    $p50 = $sorted[[math]::Floor(($sorted.Count - 1) * 0.5)]
    $p95 = $sorted[[math]::Floor(($sorted.Count - 1) * 0.95)]
    $mean = ($lat | Measure-Object -Average).Average
    $tps = if ($mean -gt 0) { $bs / ($mean / 1000.0) } else { 0 }
    $row = [pscustomobject]@{
        batch_size = $bs
        p50_ms = [math]::Round($p50, 3)
        p95_ms = [math]::Round($p95, 3)
        mean_ms = [math]::Round($mean, 3)
        throughput_samples_per_s = [math]::Round($tps, 1)
        warmup = $Warmup
        timed = $Timed
    }
    $report += $row
    Write-Host ($row | ConvertTo-Json -Compress)
}

$out = "artifacts/api_benchmark.json"
New-Item -ItemType Directory -Force -Path artifacts | Out-Null
$report | ConvertTo-Json -Depth 4 | Set-Content -Path $out -Encoding UTF8
Write-Host "Saved $out"
Write-Host "NOTE: HTTP benchmarks include network+validation+FE+preprocess+ONNX, not model-only stage1 numbers."
