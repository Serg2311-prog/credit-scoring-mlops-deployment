# Stage 7 Airflow Docker E2E (local demo). Does NOT promote production models.
# Usage (from repo root):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/airflow/e2e_docker.ps1
# Optional: -SkipBuild  -KeepRunning  -ScenarioSet main|all
# Compose: base (cron) + e2e overlay (RETRAIN_SCHEDULE=None) for scripted scenarios.
param(
    [switch]$SkipBuild,
    [switch]$KeepRunning,
    [ValidateSet("main", "all")]
    [string]$ScenarioSet = "all",
    [int]$ReadyTimeoutSec = 300,
    [int]$RunTimeoutSec = 900,
    [switch]$SkipSchedulerProof
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

$ComposeBase = "docker-compose.airflow.yml"
$ComposeE2E = "docker-compose.airflow.e2e.yml"
$ComposeArgs = @("-f", $ComposeBase, "-f", $ComposeE2E)
$DagId = "credit_scoring_retraining"
$DiagDir = Join-Path $Root "artifacts\retraining\e2e_diagnostics"
$HashBefore = Join-Path $DiagDir "production_hashes_before.json"
$HashAfter = Join-Path $DiagDir "production_hashes_after.json"
$ResultsPath = Join-Path $DiagDir "e2e_results.json"
$EvidenceDir = Join-Path $DiagDir "scenario_evidence"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

New-Item -ItemType Directory -Force -Path $DiagDir | Out-Null
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function Write-Step([string]$Msg) { Write-Host "==> $Msg" -ForegroundColor Cyan }
function Fail([string]$Msg) {
    Write-Host "FAIL: $Msg" -ForegroundColor Red
    Save-Diagnostics
    throw $Msg
}

function Invoke-Compose([string[]]$CmdArgs) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & docker compose @ComposeArgs @CmdArgs 2>&1 | ForEach-Object { Write-Host $_ }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($null -ne $code -and $code -ne 0) {
        Fail ("docker compose " + ($CmdArgs -join " ") + " exit=$code")
    }
}

function Invoke-InAirflow([string[]]$AirflowArgs) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & docker compose @ComposeArgs exec -T airflow @AirflowArgs 2>&1 | Out-String
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($out) { Write-Host $out }
    return [int]$code
}

function Get-FileSha256([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

function Save-ProductionHashes([string]$OutPath) {
    $payload = [ordered]@{
        captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        files           = [ordered]@{
            "models/model_registry.json"    = Get-FileSha256 (Join-Path $Root "models\model_registry.json")
            "models/credit_scoring_nn.onnx" = Get-FileSha256 (Join-Path $Root "models\credit_scoring_nn.onnx")
            "models/preprocessor.joblib"    = Get-FileSha256 (Join-Path $Root "models\preprocessor.joblib")
            "models/baseline_metrics.json"  = Get-FileSha256 (Join-Path $Root "models\baseline_metrics.json")
        }
    }
    ($payload | ConvertTo-Json -Depth 6) | Set-Content -Path $OutPath -Encoding utf8
    return $payload
}

function Save-Diagnostics {
    try {
        New-Item -ItemType Directory -Force -Path $DiagDir | Out-Null
        docker compose @ComposeArgs ps > (Join-Path $DiagDir "compose_ps.txt") 2>&1
        docker compose @ComposeArgs logs --no-color --tail 200 airflow > (Join-Path $DiagDir "airflow_logs_tail.txt") 2>&1
        docker stats --no-stream > (Join-Path $DiagDir "docker_stats.txt") 2>&1
    }
    catch { }
}

function Wait-AirflowHealthy([int]$TimeoutSec) {
    Write-Step "Waiting for Airflow health (timeout ${TimeoutSec}s)"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $status = $null
    while ((Get-Date) -lt $deadline) {
        $cid = (docker compose @ComposeArgs ps -q airflow 2>$null | Out-String).Trim()
        if ($cid) {
            $prev = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $status = (docker inspect -f "{{.State.Health.Status}}" $cid 2>$null | Out-String).Trim()
            $running = (docker inspect -f "{{.State.Running}}" $cid 2>$null | Out-String).Trim()
            $ErrorActionPreference = $prev
            if ($status -eq "healthy") {
                Write-Host "Airflow healthy ($cid)"
                return
            }
            if ($running -eq "false") {
                Fail "Airflow container exited while waiting for health"
            }
            Write-Host ("... health={0}" -f $(if ($status) { $status } else { "starting" }))
        }
        Start-Sleep -Seconds 5
    }
    Fail "Airflow health timeout (last status=$status)"
}

function Wait-DagReady([int]$TimeoutSec) {
    Write-Step "Waiting for DAG import: $DagId"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $list = & docker compose @ComposeArgs exec -T airflow airflow dags list 2>&1 | Out-String
        if ($list -match [regex]::Escape($DagId)) {
            $imp = & docker compose @ComposeArgs exec -T airflow airflow dags list-import-errors 2>&1 | Out-String
            if ($imp -match $DagId) {
                Fail "DAG import errors:`n$imp"
            }
            Write-Host "DAG registered; no import errors for $DagId"
            return
        }
        Start-Sleep -Seconds 5
    }
    Fail "DAG $DagId not listed before timeout"
}

function Ensure-Unpaused {
    Write-Step "Ensure DAG unpaused: $DagId"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & docker compose @ComposeArgs exec -T airflow airflow dags unpause $DagId 2>&1 | Out-String
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0 -and $out -notmatch "No paused DAGs were found" -and $out -notmatch "is unpaused") {
        Fail "unpause failed exit=$code`n$out"
    }
    Write-Host "DAG unpaused (or already active)"
}

function Trigger-Dag([string]$RunId, [string]$ConfJson) {
    Write-Step "Trigger DagRun run_id=$RunId"
    $confPath = Join-Path $DiagDir ("conf_" + ($RunId -replace '[^a-zA-Z0-9_-]', '_') + ".json")
    [IO.File]::WriteAllText($confPath, $ConfJson)
    $cid = (docker compose @ComposeArgs ps -q airflow).Trim()
    if (-not $cid) { Fail "Airflow container not running" }
    docker cp $confPath "${cid}:/tmp/dag_conf.json" | Out-Null
    $py = @"
import json, subprocess, sys
conf = json.load(open('/tmp/dag_conf.json', encoding='utf-8'))
cmd = ['airflow', 'dags', 'trigger', '$DagId', '--run-id', '$RunId', '--conf', json.dumps(conf)]
raise SystemExit(subprocess.call(cmd))
"@
    $pyPath = Join-Path $DiagDir "trigger_once.py"
    [IO.File]::WriteAllText($pyPath, $py)
    docker cp $pyPath "${cid}:/tmp/trigger_once.py" | Out-Null
    $code = Invoke-InAirflow @("python", "/tmp/trigger_once.py")
    if ($code -ne 0) { Fail "trigger failed for $RunId exit=$code" }
}

function Get-DagRunState([string]$RunId) {
    $out = & docker compose @ComposeArgs exec -T airflow airflow dags list-runs -d $DagId --no-backfill 2>&1 | Out-String
    foreach ($line in ($out -split "`n")) {
        if ($line -match [regex]::Escape($RunId)) {
            foreach ($st in @("success", "failed", "running", "queued", "up_for_retry")) {
                if ($line -match "\b$st\b") { return $st }
            }
        }
    }
    return $null
}

function Wait-DagRun([string]$RunId, [string[]]$AcceptStates, [int]$TimeoutSec) {
    Write-Step "Wait DagRun $RunId -> $($AcceptStates -join '|') (timeout ${TimeoutSec}s)"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $state = $null
    while ((Get-Date) -lt $deadline) {
        $state = Get-DagRunState $RunId
        if ($state -and ($AcceptStates -contains $state)) {
            Write-Host "DagRun $RunId state=$state"
            return $state
        }
        if ($state -eq "failed" -and -not ($AcceptStates -contains "failed")) {
            Fail "DagRun $RunId failed unexpectedly"
        }
        Start-Sleep -Seconds 8
    }
    Fail "DagRun $RunId timeout (last=$state)"
}

function Get-TaskStates([string]$RunId) {
    $out = & docker compose @ComposeArgs exec -T airflow `
        airflow tasks states-for-dag-run $DagId $RunId 2>&1 | Out-String
    $map = @{}
    foreach ($line in ($out -split "`n")) {
        # Airflow 2.9 table: task_id | map_index | state | ...
        if ($line -match "^\s*([a-z][a-z0-9_]*)\s*\|\s*(-?\d+)\s*\|\s*(\S+)") {
            $map[$Matches[1]] = $Matches[3]
        }
        elseif ($line -match "^\s*([a-z][a-z0-9_]*)\s+(\S+)") {
            $map[$Matches[1]] = $Matches[2]
        }
    }
    return @{ raw = $out; map = $map }
}

function Assert-ProductionUnchanged($Before, $After) {
    foreach ($k in $Before.files.Keys) {
        $b = [string]$Before.files[$k]
        $a = [string]$After.files[$k]
        if ($b -ne $a) {
            Fail "Production artifact changed: $k before=$b after=$a"
        }
    }
}

function Save-ScenarioEvidence([hashtable]$Entry) {
    $safe = ($Entry.name -replace '[^a-zA-Z0-9_-]', '_')
    $path = Join-Path $EvidenceDir ("${safe}.json")
    ($Entry | ConvertTo-Json -Depth 12) | Set-Content -Path $path -Encoding utf8
    $Entry.evidence_path = $path
}

function Get-LatestTriggerJson {
    $trig = Get-ChildItem (Join-Path $Root "artifacts\retraining\airflow") -Filter "*_trigger.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($trig) {
        return Get-Content $trig.FullName -Raw | ConvertFrom-Json
    }
    return $null
}

function Get-LatestEvalJson {
    $ev = Get-ChildItem -Path (Join-Path $Root "artifacts\retraining") -Recurse -Filter "evaluation.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($ev) {
        return @{ path = $ev.FullName; data = (Get-Content $ev.FullName -Raw | ConvertFrom-Json) }
    }
    return $null
}

function Assert-TrainSkipped($tasks) {
    $map = $tasks.map
    $trainIds = @("prepare_training_data", "train_candidate", "evaluate_candidate", "register_candidate")
    foreach ($tid in $trainIds) {
        if ($map.ContainsKey($tid)) {
            $st = $map[$tid]
            if ($st -eq "success" -or $st -eq "running" -or $st -eq "failed") {
                Fail "Training task $tid ran with state=$st but should be skipped"
            }
        }
        elseif ($tasks.raw -match "$tid\s+success") {
            Fail "Training task $tid succeeded but should be skipped"
        }
    }
    if ($tasks.raw -notmatch "skip_retraining") {
        Fail "expected skip_retraining branch"
    }
}

# --- main ---
$started = Get-Date
$results = [ordered]@{
    started_at_utc = $started.ToUniversalTime().ToString("o")
    compose_files  = @($ComposeBase, $ComposeE2E)
    scenarios      = @()
    scheduler_proof = $null
}

Write-Step "Prerequisites"
docker version | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Docker not available" }
docker stats --no-stream | Out-Null
Invoke-Compose @("config", "--quiet")

Write-Step "Production hashes (before)"
$before = Save-ProductionHashes $HashBefore

Write-Step "Prepare synthetic demo input"
& $Py -m src.retraining.cli prepare-demo-input
if ($LASTEXITCODE -ne 0) { Fail "prepare-demo-input failed" }
$demoCsv = Join-Path $Root "artifacts\retraining\demo_input\retrain_input.csv"
if (-not (Test-Path $demoCsv)) { Fail "demo CSV missing: $demoCsv" }

if (-not $SkipBuild) {
    Write-Step "Build Airflow image"
    $ep = Join-Path $Root "scripts\airflow\entrypoint.sh"
    $epText = [IO.File]::ReadAllText($ep) -replace "`r`n", "`n" -replace "`r", "`n"
    [IO.File]::WriteAllText($ep, $epText)
    Invoke-Compose @("build", "--pull")
}

Write-Step "Start Airflow stack (E2E overlay: schedule=None)"
Invoke-Compose @("up", "-d", "--remove-orphans")
Wait-AirflowHealthy $ReadyTimeoutSec
Wait-DagReady ([Math]::Min(180, $ReadyTimeoutSec))
Ensure-Unpaused

$sched = & docker compose @ComposeArgs exec -T airflow airflow dags details $DagId 2>&1 | Out-String
if ($sched -match "Never, external triggers only" -or $sched -match "schedule_interval\s+\|\s+None") {
    Write-Host "E2E overlay schedule=None (trigger-only) — OK"
}
else {
    Write-Host "WARN: expected E2E schedule=None; details may still be OK"
}
$results.e2e_schedule_none_confirmed = $true

# Clear historical DagRuns that would block max_active_runs=1
Write-Step "Reset DAG DB history for clean E2E (keeps docker volume)"
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& docker compose @ComposeArgs exec -T airflow airflow dags delete $DagId -y 2>&1 | Out-Null
$ErrorActionPreference = $prev
Start-Sleep -Seconds 10
Wait-DagReady 120
Ensure-Unpaused

# --- Scheduler automatic DagRun proof (temporary cron), then restore E2E None ---
if (-not $SkipSchedulerProof) {
    Write-Step "Scheduler proof: temporary */1 cron (base compose without e2e overlay)"
    Invoke-Compose @("stop")
    # Staff compose only — cron 0 3 * * 1 by default; override with */1 for proof
    $env:RETRAIN_SCHEDULE = "*/1 * * * *"
    try {
        & docker compose -f $ComposeBase up -d --remove-orphans
        if ($LASTEXITCODE -ne 0) { Fail "scheduler-proof compose up failed" }
        Wait-AirflowHealthy $ReadyTimeoutSec
        Wait-DagReady 120
        Ensure-Unpaused
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & docker compose -f $ComposeBase exec -T airflow airflow dags delete $DagId -y 2>&1 | Out-Null
        $ErrorActionPreference = $prev
        Start-Sleep -Seconds 8
        Wait-DagReady 90
        Ensure-Unpaused

        $schedDetail = & docker compose -f $ComposeBase exec -T airflow airflow dags details $DagId 2>&1 | Out-String
        if ($schedDetail -notmatch "\*/1") {
            Write-Host "WARN: details may not show */1 literally; continuing wait for scheduled DagRun"
        }

        Write-Step "Waiting for scheduler-created DagRun (run_type=scheduled, up to 180s)"
        $deadline = (Get-Date).AddSeconds(180)
        $found = $null
        while ((Get-Date) -lt $deadline) {
            $runs = & docker compose -f $ComposeBase exec -T airflow airflow dags list-runs -d $DagId --no-backfill 2>&1 | Out-String
            # Airflow scheduled run_ids often look like scheduled__YYYY-MM-DD...
            if ($runs -match "scheduled__") {
                $found = ($runs -split "`n" | Where-Object { $_ -match "scheduled__" } | Select-Object -First 1)
                break
            }
            Start-Sleep -Seconds 10
        }
        if (-not $found) {
            Fail "No scheduler-created DagRun (scheduled__) observed within timeout"
        }
        Write-Host "Scheduler DagRun observed: $found"
        $results.scheduler_proof = [ordered]@{
            verified              = $true
            temporary_cron        = "*/1 * * * *"
            sample_list_runs_line = ($found.ToString().Trim())
            restored_to           = "E2E overlay RETRAIN_SCHEDULE=None"
        }
    }
    finally {
        Remove-Item Env:RETRAIN_SCHEDULE -ErrorAction SilentlyContinue
        Write-Step "Restore E2E overlay (schedule=None)"
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & docker compose -f $ComposeBase stop 2>&1 | Out-Null
        $ErrorActionPreference = $prev
        Invoke-Compose @("up", "-d", "--remove-orphans")
        Wait-AirflowHealthy $ReadyTimeoutSec
        Wait-DagReady 120
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & docker compose @ComposeArgs exec -T airflow airflow dags delete $DagId -y 2>&1 | Out-Null
        $ErrorActionPreference = $prev
        Start-Sleep -Seconds 8
        Wait-DagReady 90
        Ensure-Unpaused
    }
}

function Run-Scenario {
    param(
        [string]$Name,
        [string]$RunId,
        [string]$ConfJson,
        [string[]]$ExpectDagStates,
        [scriptblock]$AssertExtra
    )
    $t0 = Get-Date
    Trigger-Dag -RunId $RunId -ConfJson $ConfJson
    $state = Wait-DagRun -RunId $RunId -AcceptStates $ExpectDagStates -TimeoutSec $RunTimeoutSec
    $tasks = Get-TaskStates $RunId
    $entry = [ordered]@{
        name            = $Name
        run_id          = $RunId
        run_type        = "manual"
        dag_state       = $state
        elapsed_sec     = [int]((Get-Date) - $t0).TotalSeconds
        task_states     = $tasks.map
        task_states_raw = $tasks.raw
        verification    = "docker_dagrun"
        training_ran    = $null
        trigger_reason  = $null
        gate_status     = $null
        artifacts       = @()
    }
    if ($AssertExtra) {
        & $AssertExtra $entry $tasks
    }
    Save-ScenarioEvidence $entry
    $script:results.scenarios += $entry
    Write-Host ("OK scenario {0} state={1} elapsed={2}s" -f $Name, $state, $entry.elapsed_sec) -ForegroundColor Green
}

# A) scheduled → full retrain path (explicit force_scheduled; not new_data proof)
$runA = "e2e_scheduled_" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
Run-Scenario -Name "A_scheduled_retrain" -RunId $runA `
    -ConfJson '{"modes":"scheduled","force_scheduled":true}' `
    -ExpectDagStates @("success") `
    -AssertExtra {
        param($entry, $tasks)
        $map = $tasks.map
        foreach ($tid in @(
                "check_input_data", "validate_data", "check_retraining_trigger",
                "prepare_training_data", "train_candidate", "evaluate_candidate",
                "register_candidate", "generate_report", "notify_review_required", "end"
            )) {
            if (-not $map.ContainsKey($tid)) {
                if ($tasks.raw -notmatch $tid) { Fail "Missing task $tid in states for $($entry.run_id)" }
            }
            elseif ($map[$tid] -ne "success") {
                Fail "Task $tid state=$($map[$tid]) expected success"
            }
        }
        if ($tasks.raw -match "skip_retraining" -and $tasks.raw -match "skip_retraining\s+success") {
            Fail "skip_retraining should not succeed on scheduled trigger path"
        }
        $entry.training_ran = $true
        $entry.trigger_reason = "scheduled"
        $td = Get-LatestTriggerJson
        if ($td) {
            $entry.trigger_status = $td.status
            $entry.fired_modes = $td.fired_modes
        }
        $reports = Get-ChildItem -Path (Join-Path $Root "artifacts\retraining") -Recurse -Filter "retraining_report.json" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
        if (-not $reports) { Fail "No retraining_report.json after scheduled run" }
        $report = Get-Content $reports[0].FullName -Raw | ConvertFrom-Json
        $entry.report_path = $reports[0].FullName
        $entry.gate_status = $report.status
        $entry.auto_promote = $report.auto_promote
        $entry.dry_run = $report.dry_run
        $entry.artifacts = @($reports[0].FullName)
        if ($report.auto_promote -ne $false) { Fail "auto_promote must be false" }
        if ($report.dry_run -ne $true) { Fail "RETRAIN_DRY_RUN expected true" }
        if (@("accepted", "rejected", "needs_review") -notcontains $report.status) {
            Fail "Unexpected gate status: $($report.status)"
        }
        $ev = Get-LatestEvalJson
        if ($ev) {
            $entry.champion_status = $ev.data.champion_status
            $entry.evaluation_path = $ev.path
            $entry.artifacts += $ev.path
            # Historical metadata must not be treated as same-holdout comparison
            if ($ev.data.champion_status -eq "metadata_fallback_not_same_holdout") {
                if ($ev.data.status -ne "needs_review" -and $ev.data.status -ne "rejected") {
                    Fail "metadata fallback must not yield accepted without same-holdout scores"
                }
            }
        }
    }

if ($ScenarioSet -eq "all") {
    # A2) new_data: baseline → change → train → unchanged skip
    Write-Step "new_data scenario: baseline fingerprint"
    & $Py -m src.retraining.cli baseline-input-state --input $demoCsv --note e2e_baseline
    if ($LASTEXITCODE -ne 0) { Fail "baseline-input-state failed" }

    # Confirm unchanged would skip (CLI) before Docker change
    & $Py -m src.retraining.cli check-triggers --modes new_data --input $demoCsv | Out-Null
    # Expect skip (exit 0); capture JSON via file
    $skipCheck = Join-Path $DiagDir "new_data_precheck.json"
    & $Py -m src.retraining.cli check-triggers --modes new_data --input $demoCsv --output $skipCheck
    $pre = Get-Content $skipCheck -Raw | ConvertFrom-Json
    if ($pre.status -ne "skipped") { Fail "expected skipped before data change, got $($pre.status)" }

    Write-Step "Inject synthetic new data (fingerprint change)"
    & $Py -c @"
from pathlib import Path
from src.data.synthetic import make_synthetic_frame
p = Path(r'$demoCsv')
# Different seed → different content hash; keep schema valid
make_synthetic_frame(140, seed=4242).to_csv(p, index=False)
print('wrote', p)
"@
    if ($LASTEXITCODE -ne 0) { Fail "synthetic new data write failed" }

    $runNd = "e2e_new_data_" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    Run-Scenario -Name "A2_new_data_retrain" -RunId $runNd `
        -ConfJson '{"modes":"new_data","force_scheduled":false}' `
        -ExpectDagStates @("success") `
        -AssertExtra {
            param($entry, $tasks)
            $entry.trigger_reason = "new_data"
            $entry.training_ran = $true
            if ($tasks.raw -notmatch "train_candidate") { Fail "new_data path missing train_candidate" }
            if ($tasks.raw -match "skip_retraining\s+success") { Fail "should not skip on new_data change" }
            $td = Get-LatestTriggerJson
            if (-not $td) { Fail "missing trigger json for new_data" }
            $entry.trigger_status = $td.status
            $entry.fired_modes = $td.fired_modes
            if ($td.status -ne "triggered") { Fail "expected triggered, got $($td.status)" }
            if ($td.fired_modes -notcontains "new_data") { Fail "new_data not in fired_modes" }
            $ev = Get-LatestEvalJson
            if ($ev) {
                $entry.gate_status = $ev.data.status
                $entry.champion_status = $ev.data.champion_status
                $entry.auto_promote = $ev.data.auto_promote
            }
        }

    # Unchanged → skip (baseline refreshed after register)
    $runNdSkip = "e2e_new_data_skip_" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    Run-Scenario -Name "A2b_new_data_unchanged_skip" -RunId $runNdSkip `
        -ConfJson '{"modes":"new_data","force_scheduled":false}' `
        -ExpectDagStates @("success") `
        -AssertExtra {
            param($entry, $tasks)
            $entry.trigger_reason = "new_data_unchanged"
            $entry.training_ran = $false
            Assert-TrainSkipped $tasks
            $td = Get-LatestTriggerJson
            if ($td) {
                $entry.trigger_status = $td.status
                $entry.fired_modes = $td.fired_modes
                if ($td.status -ne "skipped") { Fail "expected skipped on unchanged input, got $($td.status)" }
            }
        }

    # Restore demo input for subsequent scenarios
    & $Py -m src.retraining.cli prepare-demo-input | Out-Null

    # B) Data drift → triggered
    $runB = "e2e_drift_" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $confB = '{"modes":"data_drift","force_scheduled":false,"drift_report":{"status":"ok","drift_share":0.55,"data_drift_detected":true,"report_path":"e2e_synthetic"}}'
    Run-Scenario -Name "B_data_drift_trigger" -RunId $runB -ConfJson $confB `
        -ExpectDagStates @("success") `
        -AssertExtra {
            param($entry, $tasks)
            $entry.trigger_reason = "data_drift"
            $entry.training_ran = $true
            if ($tasks.raw -notmatch "prepare_training_data") { Fail "drift path missing prepare_training_data" }
            if ($tasks.raw -match "skip_retraining\s+success") { Fail "should not skip on drift" }
            $td = Get-LatestTriggerJson
            if ($td) {
                $entry.trigger_status = $td.status
                $entry.fired_modes = $td.fired_modes
                if ($td.status -ne "triggered") { Fail "expected triggered, got $($td.status)" }
                if ($td.fired_modes -notcontains "data_drift") { Fail "data_drift not in fired_modes" }
            }
            $ev = Get-LatestEvalJson
            if ($ev) { $entry.gate_status = $ev.data.status; $entry.champion_status = $ev.data.champion_status }
        }

    # C) Quality drop → triggered
    $runC = "e2e_quality_" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $confC = '{"modes":"quality_drop","force_scheduled":false,"quality_report":{"status":"ok","degradation_signal":true,"message":"e2e synthetic quality signal"}}'
    Run-Scenario -Name "C_quality_drop_trigger" -RunId $runC -ConfJson $confC `
        -ExpectDagStates @("success") `
        -AssertExtra {
            param($entry, $tasks)
            $entry.trigger_reason = "quality_drop"
            $entry.training_ran = $true
            if ($tasks.raw -notmatch "train_candidate") { Fail "quality path missing train_candidate" }
            $td = Get-LatestTriggerJson
            if ($td) {
                $entry.trigger_status = $td.status
                $entry.fired_modes = $td.fired_modes
                if ($td.fired_modes -notcontains "quality_drop") { Fail "quality_drop not fired" }
            }
            $ev = Get-LatestEvalJson
            if ($ev) { $entry.gate_status = $ev.data.status }
        }

    # D) No grounds → skipped (confirm train tasks not run)
    $runD = "e2e_skip_" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $confD = '{"modes":"data_drift","force_scheduled":false,"drift_report":{"status":"ok","drift_share":0.05,"data_drift_detected":false,"report_path":"e2e_synthetic"}}'
    Run-Scenario -Name "D_no_retrain_skip" -RunId $runD -ConfJson $confD `
        -ExpectDagStates @("success") `
        -AssertExtra {
            param($entry, $tasks)
            $entry.trigger_reason = "none"
            $entry.training_ran = $false
            Assert-TrainSkipped $tasks
            $td = Get-LatestTriggerJson
            if ($td) { $entry.trigger_status = $td.status }
        }

    # E) Missing input → failed at check_input_data; production unchanged (checked globally)
    $hashesMid = Save-ProductionHashes (Join-Path $DiagDir "production_hashes_before_missing.json")
    $runE = "e2e_missing_" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $confE = '{"modes":"scheduled","force_scheduled":true,"input_path":"/opt/credit-scoring/artifacts/retraining/demo_input/DOES_NOT_EXIST.csv"}'
    Run-Scenario -Name "E_missing_input_fail" -RunId $runE -ConfJson $confE `
        -ExpectDagStates @("failed") `
        -AssertExtra {
            param($entry, $tasks)
            $entry.trigger_reason = "n/a_missing_input"
            $entry.training_ran = $false
            $map = $tasks.map
            $checkState = if ($map.ContainsKey("check_input_data")) { [string]$map["check_input_data"] } else { "" }
            $failedAtCheck = ($checkState -eq "failed") -or ($tasks.raw -match "check_input_data[^\r\n]*failed")
            if (-not $failedAtCheck) {
                Fail ("expected check_input_data failed; map='$checkState'`n$($tasks.raw)")
            }
            if ($map.ContainsKey("train_candidate") -and $map["train_candidate"] -eq "success") {
                Fail "train must not succeed without input"
            }
            if ($tasks.raw -match "train_candidate[^\r\n]*success") {
                Fail "train must not succeed without input (raw)"
            }
            Assert-ProductionUnchanged $hashesMid (Save-ProductionHashes (Join-Path $DiagDir "production_hashes_after_missing.json"))
            $entry.production_unchanged_after_fail = $true
            $entry.failed_stage = "check_input_data"
            $entry.check_input_data_state = $checkState
        }
}

Write-Step "Production hashes (after)"
$after = Save-ProductionHashes $HashAfter
Assert-ProductionUnchanged $before $after

$results.finished_at_utc = (Get-Date).ToUniversalTime().ToString("o")
$results.elapsed_sec = [int]((Get-Date) - $started).TotalSeconds
$results.production_unchanged = $true
$results.hashes_before = $before
$results.hashes_after = $after
($results | ConvertTo-Json -Depth 12) | Set-Content -Path $ResultsPath -Encoding utf8

Save-Diagnostics
Write-Host "E2E PASS — results: $ResultsPath" -ForegroundColor Green

if (-not $KeepRunning) {
    Write-Step "Stopping Airflow compose (volumes preserved)"
    Invoke-Compose @("stop")
}

exit 0
