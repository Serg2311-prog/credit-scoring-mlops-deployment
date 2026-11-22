# Local reproduction of CI Python quality gates (Windows PowerShell 5.1+).
param(
    [switch]$SkipGenerate,
    [switch]$ForceSynthetic
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$env:PYTHONPATH = $Root

function Assert-Exit([string]$Label) {
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "FAILED: $Label (exit $LASTEXITCODE)"
    }
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "==> Python: $py"

$onnx = Join-Path $Root "models\credit_scoring_nn.onnx"
$prep = Join-Path $Root "models\preprocessor.joblib"
$marker = Join-Path $Root "models\CI_SYNTHETIC_ARTIFACTS.json"

if (-not $SkipGenerate) {
    $needGenerate = $ForceSynthetic -or -not (Test-Path $onnx) -or -not (Test-Path $prep)
    if ($needGenerate) {
        Write-Host "==> Generate synthetic artifacts into models/"
        $genArgs = @(
            "scripts\ci\generate_synthetic_artifacts.py",
            "--output-dir", "models"
        )
        if ($ForceSynthetic) { $genArgs += "--force" }
        & $py @genArgs
        Assert-Exit "generate_synthetic_artifacts"
        & $py "scripts\ci\verify_artifacts.py" "--dir" "models" "--allow-synthetic"
        Assert-Exit "verify_artifacts"
    }
    else {
        Write-Host "==> Using existing models/ artifacts (marker present: $(Test-Path $marker))"
    }
}

Write-Host "==> black"
& $py -m black --check src tests scripts\ci
Assert-Exit "black"

Write-Host "==> flake8"
& $py -m flake8 src tests scripts\ci
Assert-Exit "flake8"

Write-Host "==> pytest (not k8s/e2e)"
New-Item -ItemType Directory -Force -Path "artifacts\ci" | Out-Null
& $py -m pytest -v -m "not k8s and not e2e" --tb=short --junitxml=artifacts\ci\pytest-local.xml
Assert-Exit "pytest"

Write-Host "OK: local CI Python checks passed"
