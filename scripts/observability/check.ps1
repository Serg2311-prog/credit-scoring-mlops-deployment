# Stage 5 observability stack checks (Windows PowerShell 5.1+).
param(
    [switch]$SkipComposeConfig,
    [switch]$SkipPromtool,
    [int]$VerifyRetries = 12,
    [double]$VerifySleepSeconds = 5
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Assert-Exit([string]$Label) {
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "FAILED: $Label (exit $LASTEXITCODE)"
    }
}

Write-Host "==> Compose config validation"
if (-not $SkipComposeConfig) {
    docker compose -f docker-compose.yml -f docker-compose.observability.yml config --quiet
    Assert-Exit "docker compose config"
    Write-Host "[PASS] compose config"
}

Write-Host "==> promtool check rules/config"
if (-not $SkipPromtool) {
    docker run --rm --entrypoint promtool `
        -v "${Root}/monitoring/prometheus:/etc/prometheus:ro" `
        prom/prometheus:v3.2.1 `
        check config /etc/prometheus/prometheus.yml
    Assert-Exit "promtool check config"
    docker run --rm --entrypoint promtool `
        -v "${Root}/monitoring/prometheus:/etc/prometheus:ro" `
        prom/prometheus:v3.2.1 `
        check rules /etc/prometheus/alerts.yml
    Assert-Exit "promtool check rules"
    Write-Host "[PASS] promtool"
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "==> HTTP stack verification (retries=$VerifyRetries)"
& $py "scripts\observability\verify_stack.py" --retries $VerifyRetries --sleep $VerifySleepSeconds
Assert-Exit "verify_stack.py"

Write-Host "OK: observability checks passed"
