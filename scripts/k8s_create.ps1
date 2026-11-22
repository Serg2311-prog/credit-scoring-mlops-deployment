# Create local kind cluster (idempotent if already exists).
param(
    [switch]$ForceRecreate
)

. "$PSScriptRoot\k8s_common.ps1"

Write-Step "Checking prerequisites"
Assert-DockerRunning
Assert-Command kubectl
$kindExe = Get-KindExe
Write-Host ("kind: {0}" -f $kindExe)
Write-Host ("kubectl: {0}" -f (Get-Command kubectl).Source)
docker version --format "Docker Server: {{.Server.Version}}"
Assert-LastExitCode "docker version"

$clusters = Invoke-Native -FilePath $kindExe -Arguments @("get", "clusters")
if ($clusters.ExitCode -ne 0 -and $clusters.Text -notmatch "No kind clusters found") {
    throw ("FAILED: kind get clusters (exit code {0}): {1}" -f $clusters.ExitCode, $clusters.Text)
}
$exists = $false
foreach ($line in $clusters.Output) {
    if ($line.Trim() -eq $script:ClusterName) {
        $exists = $true
        break
    }
}

if ($exists -and -not $ForceRecreate) {
    Write-Step ("Cluster '{0}' already exists — reusing (pass -ForceRecreate to delete+create)" -f $script:ClusterName)
    Set-KindKubeContext -KindExe $kindExe
    kubectl get nodes
    Assert-LastExitCode "kubectl get nodes"
    Write-Host "OK: cluster ready"
    exit 0
}

if ($exists -and $ForceRecreate) {
    Write-Step ("Deleting existing cluster '{0}'" -f $script:ClusterName)
    & $kindExe delete cluster --name $script:ClusterName
    Assert-LastExitCode "kind delete cluster"
}

Write-Step ("Creating kind cluster '{0}'" -f $script:ClusterName)
& $kindExe create cluster --config $script:KindConfig --wait 120s
Assert-LastExitCode "kind create cluster"
Set-KindKubeContext -KindExe $kindExe
kubectl get nodes -o wide
Assert-LastExitCode "kubectl get nodes"
Write-Host "OK: kind cluster created"
