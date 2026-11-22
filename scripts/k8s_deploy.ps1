# Apply Kustomize overlay and wait for rollout.
. "$PSScriptRoot\k8s_common.ps1"

Write-Step "Checking prerequisites"
Assert-Command kubectl
$kindExe = Get-KindExe
Set-KindKubeContext -KindExe $kindExe

Write-Step "Rendering kustomize overlay"
kubectl kustomize $script:OverlayPath | Out-Null
Assert-LastExitCode "kubectl kustomize"

Write-Step "Applying manifests"
kubectl apply -k $script:OverlayPath
Assert-LastExitCode "kubectl apply -k"

Write-Step "Waiting for Deployment rollout"
kubectl -n $script:Namespace rollout status ("deployment/{0}" -f $script:DeploymentName) --timeout=180s
Assert-LastExitCode "kubectl rollout status"

Write-Step "Resources"
kubectl -n $script:Namespace get pods -o wide
Assert-LastExitCode "kubectl get pods"
kubectl -n $script:Namespace get deployments,services
Assert-LastExitCode "kubectl get deployments,services"

kubectl -n $script:Namespace get pods -l "app.kubernetes.io/name=credit-scoring-api" -o wide
Assert-LastExitCode "kubectl get pods by label"
Write-Host "OK: deployment applied"
