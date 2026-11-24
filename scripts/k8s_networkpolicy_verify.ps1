# NetworkPolicy verification helper.
# kind default CNI (kindnet) typically does NOT enforce NetworkPolicy.
# This script:
#  1) validates selectors/ports in rendered manifests
#  2) reports CNI / enforcement capability
#  3) provides optional allow/deny probes when a Policy-capable CNI is present
param(
    [switch]$AttemptTrafficProbes
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "==> Render kustomize and inspect NetworkPolicy"
$yaml = & kubectl kustomize (Join-Path $Root "k8s\overlays\local")
if ($LASTEXITCODE -ne 0) { throw "kustomize failed" }
# PowerShell 5.1: kubectl may return Object[] lines — normalize to one string.
$text = if ($yaml -is [System.Array]) { ($yaml -join "`n") } else { [string]$yaml }
foreach ($name in @("default-deny-ingress", "allow-frontend", "allow-api")) {
    if ($text -notmatch ("name:\s*" + [regex]::Escape($name))) {
        throw "missing NetworkPolicy $name in render"
    }
}
if ($text -notmatch "ingress-nginx") { throw "allow rules must reference ingress-nginx" }
if ($text -notmatch "credit-scoring-frontend") { throw "allow-api must allow frontend" }
if ($text -notmatch "port: 8000") { throw "API port 8000 missing" }
if ($text -notmatch "port: 8080") { throw "frontend port 8080 missing" }
Write-Host "OK NetworkPolicy selectors/ports present in render"

Write-Host "==> Detect cluster CNI / enforcement"
$cni = "unknown"
try {
    $ds = kubectl get ds -A -o name 2>$null
    if ($ds -match "calico") { $cni = "calico" }
    elseif ($ds -match "cilium") { $cni = "cilium" }
    elseif ($ds -match "kindnet") { $cni = "kindnet" }
} catch {}
Write-Host "Detected CNI hint: $cni"

$enforced = $false
if ($cni -in @("calico", "cilium")) { $enforced = $true }

if (-not $AttemptTrafficProbes) {
    Write-Host "SKIP traffic probes (pass -AttemptTrafficProbes on Calico/Cilium)"
    Write-Host "NETWORKPOLICY_STATUS=manifests_verified enforcement=$enforced cni=$cni"
    exit 0
}

if (-not $enforced) {
    Write-Host "CNI '$cni' is not Policy-enforcing; refuse to claim deny/allow traffic results"
    Write-Host "NETWORKPOLICY_STATUS=manifests_verified enforcement=false cni=$cni"
    exit 0
}

Write-Host "==> Allow probe: curl API from a frontend-labeled ephemeral pod"
# Placeholder for Calico/Cilium environments — create temporary client pods.
Write-Host "Implement cluster-specific probes here when Calico/Cilium is installed."
Write-Host "NETWORKPOLICY_STATUS=manifests_verified enforcement=true cni=$cni probes=manual"
