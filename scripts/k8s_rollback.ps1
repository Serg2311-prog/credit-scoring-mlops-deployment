# Trigger a Deployment revision, then rollback via kubectl rollout undo.
param(
    [switch]$SkipUndo
)

. "$PSScriptRoot\k8s_common.ps1"

Write-Step "Checking prerequisites"
Assert-Command kubectl
$kindExe = Get-KindExe
Set-KindKubeContext -KindExe $kindExe

Write-Step "Current rollout history"
kubectl -n $script:Namespace rollout history ("deployment/{0}" -f $script:DeploymentName)
Assert-LastExitCode "rollout history"

$stamp = Get-Date -Format "yyyyMMddHHmmss"
Write-Step ("Triggering rollout via pod-template annotation stamp={0}" -f $stamp)

# Write patch to a file to avoid PowerShell JSON quoting issues.
$patchPath = Join-Path $env:TEMP ("k8s-rollout-patch-{0}.json" -f $stamp)
$patchJson = '{"spec":{"template":{"metadata":{"annotations":{"stage3a.rollout-stamp":"' + $stamp + '"}}}}}'
Set-Content -Path $patchPath -Value $patchJson -Encoding Ascii

kubectl -n $script:Namespace patch deployment $script:DeploymentName --type merge --patch-file $patchPath
Assert-LastExitCode "patch deployment for rollout"

Write-Step "Waiting for new rollout"
$timeoutFlag = "--timeout=180s"
kubectl -n $script:Namespace rollout status ("deployment/{0}" -f $script:DeploymentName) $timeoutFlag
Assert-LastExitCode "rollout status after patch"

if ($SkipUndo) {
    Write-Host "SkipUndo set — leaving current revision"
    exit 0
}

Write-Step "Rolling back to previous revision"
kubectl -n $script:Namespace rollout undo ("deployment/{0}" -f $script:DeploymentName)
Assert-LastExitCode "rollout undo"

kubectl -n $script:Namespace rollout status ("deployment/{0}" -f $script:DeploymentName) $timeoutFlag
Assert-LastExitCode "rollout status after undo"

kubectl -n $script:Namespace rollout history ("deployment/{0}" -f $script:DeploymentName)
Assert-LastExitCode "rollout history final"
Write-Host "OK: rollout + rollback completed"
