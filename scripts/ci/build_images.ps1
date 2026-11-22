# Build API + models images locally (uses synthetic artifacts if models/ empty).
param(
    [string]$ApiTag = "credit-scoring-api:ci",
    [string]$ModelsTag = "credit-scoring-models:ci",
    [switch]$ForceSynthetic
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Assert-Exit([string]$Label) {
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "FAILED: $Label (exit $LASTEXITCODE)"
    }
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$onnx = Join-Path $Root "models\credit_scoring_nn.onnx"
$prep = Join-Path $Root "models\preprocessor.joblib"
if (-not (Test-Path $onnx) -or -not (Test-Path $prep) -or $ForceSynthetic) {
    Write-Host "==> Generating synthetic artifacts into models/ for image build"
    $args = @("scripts\ci\generate_synthetic_artifacts.py", "--output-dir", "models")
    if ($ForceSynthetic -or ((Test-Path $onnx) -and -not (Test-Path (Join-Path $Root "models\CI_SYNTHETIC_ARTIFACTS.json")))) {
        # only force when explicitly requested
    }
    if ($ForceSynthetic) { $args += "--force" }
    & $py @args
    Assert-Exit "generate artifacts"
}

Write-Host "==> docker build API $ApiTag"
docker build -f docker/Dockerfile.api -t $ApiTag .
Assert-Exit "docker build api"

Write-Host "==> docker build models $ModelsTag"
docker build -f docker/Dockerfile.models -t $ModelsTag .
Assert-Exit "docker build models"

Write-Host "OK: images built ($ApiTag, $ModelsTag)"
