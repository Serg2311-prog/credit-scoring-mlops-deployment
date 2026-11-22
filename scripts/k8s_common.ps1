# Shared helpers for Stage 3A kind scripts (Windows PowerShell 5.1+).
# Dot-source from other scripts: . "$PSScriptRoot\k8s_common.ps1"

$ErrorActionPreference = "Stop"

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:ClusterName = "credit-scoring"
$script:Namespace = "credit-scoring"
$script:DeploymentName = "credit-scoring-api"
$script:ServiceName = "credit-scoring-api"
$script:ApiImage = "credit-scoring-api:stage3a"
$script:ModelsImage = "credit-scoring-models:stage3a"
$script:KindConfig = Join-Path $script:RepoRoot "k8s\kind\cluster.yaml"
$script:OverlayPath = Join-Path $script:RepoRoot "k8s\overlays\local"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ("==> " + $Message) -ForegroundColor Cyan
}

function Assert-LastExitCode {
    param([string]$Action)
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw ("FAILED: {0} (exit code {1})" -f $Action, $LASTEXITCODE)
    }
}

function Invoke-Native {
    # Run native EXE without treating stderr as terminating under $ErrorActionPreference=Stop.
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][object[]]$Arguments
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $FilePath @Arguments 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    $lines = @()
    foreach ($item in @($output)) {
        if ($null -eq $item) { continue }
        if ($item -is [System.Management.Automation.ErrorRecord]) {
            $lines += $item.ToString()
        }
        else {
            $lines += [string]$item
        }
    }
    return [pscustomobject]@{
        ExitCode = $code
        Output   = $lines
        Text     = ($lines -join "`n")
    }
}

function Get-KindExe {
    $localKind = Join-Path $script:RepoRoot "tools\kind.exe"
    if (Test-Path $localKind) {
        return $localKind
    }
    $cmd = Get-Command kind -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    throw @"
kind is not available.
Install a portable binary (recommended, no admin):
  New-Item -ItemType Directory -Force -Path tools | Out-Null
  curl.exe -fsSL -o tools\kind.exe https://kind.sigs.k8s.io/dl/v0.29.0/kind-windows-amd64
Or install system-wide and re-run.
"@
}

function Assert-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw ("Required command not found: {0}" -f $Name)
    }
}

function Assert-DockerRunning {
    Assert-Command docker
    docker info 1>$null 2>$null
    Assert-LastExitCode "docker info (is Docker Desktop running?)"
}

function Set-KindKubeContext {
    param([string]$KindExe)
    & $KindExe export kubeconfig --name $script:ClusterName | Out-Null
    Assert-LastExitCode "kind export kubeconfig"
    kubectl config use-context ("kind-{0}" -f $script:ClusterName) | Out-Null
    Assert-LastExitCode "kubectl config use-context"
}
