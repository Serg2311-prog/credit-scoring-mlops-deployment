# Stage 1 reproduction script (Windows PowerShell)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating venv..."
    & "C:\Users\Sergey\AppData\Local\Programs\Python\Python313\python.exe" -m venv .venv
}

.\.venv\Scripts\Activate.ps1
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
