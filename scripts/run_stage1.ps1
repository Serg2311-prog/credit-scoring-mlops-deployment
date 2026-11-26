# Stage 1 reproduction script (Windows PowerShell).
# Optional: set $env:PYTHON_EXE to a specific interpreter before running.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Test-PythonVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )
    $versionText = & $PythonExe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($versionText)) {
        throw "Failed to query Python version from: $PythonExe"
    }
    $versionText = $versionText.Trim()
    $parts = $versionText.Split('.')
    if ($parts.Count -lt 2) {
        throw "Unrecognized Python version string '$versionText' from: $PythonExe"
    }
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        throw "Python 3.11+ required (found $versionText at $PythonExe)."
    }
    return $versionText
}

function Resolve-PythonExe {
    if ($null -ne $env:PYTHON_EXE -and $env:PYTHON_EXE.Trim() -ne '') {
        $explicit = $env:PYTHON_EXE.Trim()
        if (-not (Test-Path -LiteralPath $explicit)) {
            throw "PYTHON_EXE is set to '$explicit' but the path does not exist. Fix PYTHON_EXE or unset it to use PATH discovery."
        }
        $resolved = (Resolve-Path -LiteralPath $explicit).Path
        $null = Test-PythonVersion -PythonExe $resolved
        return $resolved
    }

    foreach ($name in @('python', 'python3')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            try {
                $null = Test-PythonVersion -PythonExe $cmd.Source
                return $cmd.Source
            } catch {
                # try next candidate
            }
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $resolved = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($resolved)) {
            $exe = $resolved.Trim()
            $null = Test-PythonVersion -PythonExe $exe
            return $exe
        }
    }

    throw @"
Python interpreter not found.
Install Python 3.11+ and ensure ``python`` is on PATH, or set:
  `$env:PYTHON_EXE = 'C:\Path\To\python.exe'
"@
}

$venvPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating venv..."
    $bootstrapPython = Resolve-PythonExe
    $bootstrapVersion = Test-PythonVersion -PythonExe $bootstrapPython
    Write-Host "Using bootstrap interpreter: $bootstrapPython ($bootstrapVersion)"
    & $bootstrapPython -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv with $bootstrapPython"
    }
}

.\.venv\Scripts\Activate.ps1
$venvVersion = Test-PythonVersion -PythonExe (Join-Path (Get-Location) '.venv\Scripts\python.exe')
Write-Host "Using venv Python ($venvVersion)"
python -m pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt -r requirements-nn.txt

if (-not (Test-Path "data\raw\UCI_Credit_Card.csv")) {
    throw "Missing data\raw\UCI_Credit_Card.csv"
}

python -m src.data.make_dataset
python -m src.nn.train_nn
python -m src.nn.export_onnx
python -m src.nn.parity
python -m src.nn.quantize
python -m src.nn.benchmark --device cpu
python -m src.nn.benchmark --device cuda
pytest -v
flake8 src tests
black --check src tests
