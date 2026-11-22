# Local API smoke against docker compose or existing uvicorn.
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [switch]$ViaCompose
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Assert-Exit([string]$Label) {
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "FAILED: $Label (exit $LASTEXITCODE)"
    }
}

if ($ViaCompose) {
    Write-Host "==> docker compose up"
    docker compose up -d --build
    Assert-Exit "compose up"
    Start-Sleep -Seconds 8
}

$live = Invoke-RestMethod -Uri ($BaseUrl + "/health/live") -Method Get
if ($live.status -ne "ok") { throw "live failed" }
Write-Host "live OK"

try {
    $ready = Invoke-RestMethod -Uri ($BaseUrl + "/health/ready") -Method Get
    Write-Host ("ready: " + ($ready | ConvertTo-Json -Compress))
}
catch {
    Write-Host "ready NOT OK (model missing?) — $($_.Exception.Message)"
    throw
}

$sample = @{
    LIMIT_BAL = 20000; SEX = 2; EDUCATION = 2; MARRIAGE = 1; AGE = 24
    PAY_0 = 2; PAY_2 = 2; PAY_3 = -1; PAY_4 = -1; PAY_5 = -2; PAY_6 = -2
    BILL_AMT1 = 3913; BILL_AMT2 = 3102; BILL_AMT3 = 689
    BILL_AMT4 = 0; BILL_AMT5 = 0; BILL_AMT6 = 0
    PAY_AMT1 = 0; PAY_AMT2 = 689; PAY_AMT3 = 0; PAY_AMT4 = 0; PAY_AMT5 = 0; PAY_AMT6 = 0
}
$pred = Invoke-RestMethod -Uri ($BaseUrl + "/predict") -Method Post `
    -ContentType "application/json" -Body ($sample | ConvertTo-Json)
Write-Host ($pred | ConvertTo-Json -Compress)
Write-Host "OK: smoke passed"
