# Destroy kind cluster — requires explicit confirmation.
param(
    [string]$Confirm = ""
)

. "$PSScriptRoot\k8s_common.ps1"

Write-Step "Destroy kind cluster (explicit confirmation required)"
Assert-DockerRunning
$kindExe = Get-KindExe

if ($Confirm -ne $script:ClusterName) {
    Write-Host @"
This will DELETE the kind cluster '$($script:ClusterName)'.
Docker images on the host are NOT removed.
Docker volumes / user data are NOT removed.

Re-run with:
  .\scripts\k8s_destroy.ps1 -Confirm $($script:ClusterName)
"@
    exit 1
}

Write-Step ("Deleting cluster '{0}'" -f $script:ClusterName)
& $kindExe delete cluster --name $script:ClusterName
Assert-LastExitCode "kind delete cluster"
Write-Host "OK: cluster deleted"
