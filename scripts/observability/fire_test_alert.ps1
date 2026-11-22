# Fire a temporary test alert via Alertmanager API v2 (local only).
# Body must be a JSON array of PostableAlert objects.

$ErrorActionPreference = "Stop"

$startsAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
$payload = @(
    @{
        labels = @{
            alertname = "Stage5TestAlert"
            severity  = "warning"
            service   = "credit-scoring-api"
        }
        annotations = @{
            summary     = "Stage 5 manual test alert"
            description = "Synthetic alert to verify Alertmanager + local webhook."
        }
        startsAt = $startsAt
    }
) | ConvertTo-Json -Depth 6

# ConvertTo-Json on a single-element array may emit an object; force array wrapper if needed.
if (-not $payload.TrimStart().StartsWith("[")) {
    $payload = "[$payload]"
}

Write-Host "Posting test alert to Alertmanager..."
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9093/api/v2/alerts" `
    -ContentType "application/json" -Body $payload | Out-Null

Start-Sleep -Seconds 2
$alerts = Invoke-RestMethod -Uri "http://127.0.0.1:9093/api/v2/alerts"
$hit = @($alerts | Where-Object { $_.labels.alertname -eq "Stage5TestAlert" })
if ($hit.Count -lt 1) {
    throw "FAILED: Stage5TestAlert not visible in Alertmanager"
}
Write-Host "[PASS] Alertmanager received Stage5TestAlert"
Write-Host "UI: http://127.0.0.1:9093"
Write-Host "Webhook logs: docker logs credit-scoring-alert-webhook --tail 20"
