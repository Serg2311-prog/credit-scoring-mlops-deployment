# Build API + model-artifacts images and load them into kind.
. "$PSScriptRoot\k8s_common.ps1"

Write-Step "Checking prerequisites"
Assert-DockerRunning
Assert-Command kubectl
$kindExe = Get-KindExe

$onnx = Join-Path $script:RepoRoot "models\credit_scoring_nn.onnx"
$prep = Join-Path $script:RepoRoot "models\preprocessor.joblib"
if (-not (Test-Path $onnx)) {
    throw "Missing artifact: models\credit_scoring_nn.onnx"
}
if (-not (Test-Path $prep)) {
    throw "Missing artifact: models\preprocessor.joblib"
}

Push-Location $script:RepoRoot
try {
    Write-Step ("Building {0}" -f $script:ApiImage)
    docker build -f docker/Dockerfile.api -t $script:ApiImage .
    Assert-LastExitCode "docker build API"

    Write-Step ("Building {0}" -f $script:ModelsImage)
    docker build -f docker/Dockerfile.models -t $script:ModelsImage .
    Assert-LastExitCode "docker build models"

    Write-Step ("Loading images into kind cluster '{0}'" -f $script:ClusterName)
    & $kindExe load docker-image $script:ApiImage --name $script:ClusterName
    Assert-LastExitCode "kind load API image"
    & $kindExe load docker-image $script:ModelsImage --name $script:ClusterName
    Assert-LastExitCode "kind load models image"
}
finally {
    Pop-Location
}

Write-Host "OK: images built and loaded into kind"
