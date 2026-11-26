<#
.SYNOPSIS
  Safe, idempotent Terraform state migration for cloud-experiment SG rules.

.DESCRIPTION
  Provider 0.250.0 ImportState uses resourceid.Deconstruct → Import ID
  "<security_group_id>:<rule_id>". After import, State attribute "id" stores
  the rule_id only (see vpc_security_group_rule/resource.go ImportState).

  - Requires workspace "default" and cloud-experiment backend/key.
  - Resolves cluster/node-group IDs from Terraform state (not "first cluster").
  - Mandatory state backup under LOCALAPPDATA (UTF-8 no BOM) with JSON/lineage/serial/SHA256 checks.
  - Exact match of 12 live rules; unknown extra rules forbidden.
  - Plan gate via terraform show -json (no-op only for managed addresses).
  - No SkipPlan. No apply/destroy/state push.

.PARAMETER DryRun
  Preflight + mapping + backup checks only; no state rm/import.
#>
[CmdletBinding()]
param(
  [string]$TerraformDir = '',
  [string]$BackupDir = '',
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot 'SgPlanGate.ps1')

function Write-Step([string]$Message) { Write-Host "[STEP] $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "[OK]   $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Fail([string]$Message) { throw "[FAIL] $Message" }

function Invoke-External {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $true)][string[]]$ArgumentList,
    [switch]$AllowNonZero
  )
  $out = & $FilePath @ArgumentList 2>&1
  $code = $LASTEXITCODE
  if (-not $AllowNonZero -and $code -ne 0) {
    Fail ("{0} {1} failed exit={2}: {3}" -f $FilePath, ($ArgumentList -join ' '), $code, (($out | Out-String).Trim()))
  }
  return [pscustomobject]@{ ExitCode = $code; Output = $out; Text = (($out | Out-String)) }
}

function Get-Prop {
  param($Object, [string]$Name)
  if ($null -eq $Object) { return $null }
  if (@($Object.PSObject.Properties.Name) -contains $Name) { return $Object.$Name }
  return $null
}

function ConvertTo-IntOrNull {
  param($Value)
  if ($null -eq $Value -or $Value -eq '') { return $null }
  return [int]$Value
}

# Expected 12 rules (NodePort absent). Ports: Port single; or From/To; ICMP = no ports.
# PeerSg: 'nodes' | 'master' | $null. PredefinedTarget / Cidrs as applicable.
$RuleCatalog = @(
  @{ Address = 'module.network.yandex_vpc_security_group_rule.master_self'; Sg = 'master'; Description = 'Internal cluster communication within this SG'; Direction = 'ingress'; Protocol = 'ANY'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @(); PredefinedTarget = 'self_security_group'; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.master_lb_healthchecks'; Sg = 'master'; Description = 'Load balancer health checks (platform predefined)'; Direction = 'ingress'; Protocol = 'TCP'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @(); PredefinedTarget = 'loadbalancer_healthchecks'; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.master_api_443[0]'; Sg = 'master'; Description = 'Kubernetes API HTTPS from approved admin CIDRs only'; Direction = 'ingress'; Protocol = 'TCP'; FromPort = $null; ToPort = $null; Port = 443; Cidrs = @('ADMIN'); PredefinedTarget = $null; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.master_api_6443[0]'; Sg = 'master'; Description = 'Kubernetes API 6443 from approved admin CIDRs only'; Direction = 'ingress'; Protocol = 'TCP'; FromPort = $null; ToPort = $null; Port = 6443; Cidrs = @('ADMIN'); PredefinedTarget = $null; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.master_from_nodes'; Sg = 'master'; Description = 'Nodes to master'; Direction = 'ingress'; Protocol = 'ANY'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @(); PredefinedTarget = $null; PeerSg = 'nodes' }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.master_egress'; Sg = 'master'; Description = 'Master egress (control-plane, NTP, metric-server, managed services)'; Direction = 'egress'; Protocol = 'ANY'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @('0.0.0.0/0'); PredefinedTarget = $null; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.nodes_self'; Sg = 'nodes'; Description = 'Node-to-node within SG'; Direction = 'ingress'; Protocol = 'ANY'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @(); PredefinedTarget = 'self_security_group'; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.nodes_from_master'; Sg = 'nodes'; Description = 'Master to nodes'; Direction = 'ingress'; Protocol = 'ANY'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @(); PredefinedTarget = $null; PeerSg = 'master' }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.nodes_lb_healthchecks'; Sg = 'nodes'; Description = 'Load balancer health checks (platform predefined)'; Direction = 'ingress'; Protocol = 'TCP'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @(); PredefinedTarget = 'loadbalancer_healthchecks'; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.nodes_icmp_private'; Sg = 'nodes'; Description = 'ICMP health checks from Yandex Cloud private ranges'; Direction = 'ingress'; Protocol = 'ICMP'; FromPort = $null; ToPort = $null; Port = $null; Cidrs = @('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'); PredefinedTarget = $null; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.nodes_pod_service_cidrs'; Sg = 'nodes'; Description = 'Pod and Service CIDR traffic (cluster networking)'; Direction = 'ingress'; Protocol = 'ANY'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @('10.112.0.0/16', '10.96.0.0/16'); PredefinedTarget = $null; PeerSg = $null }
  @{ Address = 'module.network.yandex_vpc_security_group_rule.nodes_egress'; Sg = 'nodes'; Description = 'Node egress (registry pulls, OS updates)'; Direction = 'egress'; Protocol = 'ANY'; FromPort = 0; ToPort = 65535; Port = $null; Cidrs = @('0.0.0.0/0'); PredefinedTarget = $null; PeerSg = $null }
)

# Post-migration inventory: 13 baseline + 12 rule resources = 25
# (baseline excludes optional IAM extras and terraform_data.sg_rules_ready until apply).
$ExpectedRuleAddresses = @($RuleCatalog | ForEach-Object { $_.Address })
$ExpectedStateResourceCount = 25

if ([string]::IsNullOrWhiteSpace($TerraformDir)) {
  $repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
  $TerraformDir = Join-Path $repoRoot 'infra\terraform\environments\cloud-experiment'
}
if (-not (Test-Path -LiteralPath $TerraformDir)) { Fail "TerraformDir not found: $TerraformDir" }
$TerraformDir = (Resolve-Path -LiteralPath $TerraformDir).Path

if ([string]::IsNullOrWhiteSpace($BackupDir)) {
  $BackupDir = Join-Path $env:LOCALAPPDATA 'credit-scoring-mlops\tfstate-backups\cloud-experiment'
}
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# Refuse backups inside the git repo
$repoRootResolved = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($BackupDir.StartsWith($repoRootResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
  Fail 'BackupDir must be outside the repository (use LOCALAPPDATA)'
}

Write-Step "TerraformDir=$TerraformDir"
Set-Location -LiteralPath $TerraformDir

Write-Step 'Preflight: tools'
foreach ($cmd in @('terraform', 'yc')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Fail "$cmd not found in PATH" }
}
Write-Ok 'terraform + yc present'

Write-Step 'Preflight: workspace default'
$wsResult = Invoke-External -FilePath 'terraform' -ArgumentList @('workspace', 'show')
$ws = $wsResult.Text.Trim()
if ($ws -ne 'default') { Fail "workspace must be 'default' (got '$ws')" }
Write-Ok 'workspace=default'

Write-Step 'Preflight: backend expects cloud-experiment'
$backendFiles = @('backend.hcl', 'backend.tf')
$backendJoined = ''
foreach ($bf in $backendFiles) {
  $p = Join-Path $TerraformDir $bf
  if (Test-Path -LiteralPath $p) { $backendJoined += (Get-Content -LiteralPath $p -Raw) + "`n" }
}
if ($backendJoined -notmatch 'cloud-experiment') {
  Fail 'Active backend config/files must reference cloud-experiment state key/path'
}
if ($TerraformDir -notmatch 'cloud-experiment') {
  Fail 'TerraformDir must be environments/cloud-experiment'
}
Write-Ok 'backend/path targets cloud-experiment'

Write-Step 'Preflight: state list'
$stateListResult = Invoke-External -FilePath 'terraform' -ArgumentList @('state', 'list')
$stateList = @(ConvertTo-StringArray ($stateListResult.Output | ForEach-Object { "$_".Trim() } | Where-Object { $_ }))
if ($stateList.Count -lt 1) { Fail 'State is empty' }
Write-Ok ("state_resources={0}" -f $stateList.Count)

$requiredCore = @(
  'module.network.yandex_vpc_security_group.k8s_master'
  'module.network.yandex_vpc_security_group.k8s_nodes'
  'module.kubernetes.yandex_kubernetes_cluster.this'
  'module.kubernetes.yandex_kubernetes_node_group.cpu'
)
foreach ($r in $requiredCore) {
  if ($stateList -notcontains $r) { Fail "Required address missing from state: $r" }
}
Write-Ok 'core SG + Kubernetes addresses present'

function Get-StateAttrStrict {
  param([string]$Address, [string]$Attr)
  $res = Invoke-External -FilePath 'terraform' -ArgumentList @('state', 'show', '-no-color', $Address) -AllowNonZero
  if ($res.ExitCode -ne 0) {
    Fail ("terraform state show failed for {0} (exit={1}); not treated as missing. {2}" -f $Address, $res.ExitCode, $res.Text.Trim())
  }
  $m = [regex]::Match($res.Text, "(?m)^\s*$([regex]::Escape($Attr))\s*=\s*`"([^`"]+)`"")
  if (-not $m.Success) { Fail "Attribute $Attr not found on $Address (state show succeeded)" }
  return $m.Groups[1].Value
}

Write-Step 'Resolve IDs from Terraform state'
$masterSgId = Get-StateAttrStrict 'module.network.yandex_vpc_security_group.k8s_master' 'id'
$nodesSgId = Get-StateAttrStrict 'module.network.yandex_vpc_security_group.k8s_nodes' 'id'
$clusterId = Get-StateAttrStrict 'module.kubernetes.yandex_kubernetes_cluster.this' 'id'
$nodeGroupId = Get-StateAttrStrict 'module.kubernetes.yandex_kubernetes_node_group.cpu' 'id'
Write-Ok 'SG + cluster + node-group IDs resolved from state'

Write-Step 'Preflight: cloud objects match state IDs (read-only)'
$cl = Invoke-External -FilePath 'yc' -ArgumentList @('managed-kubernetes', 'cluster', 'get', '--id', $clusterId, '--format', 'json')
$clusterObj = $cl.Text | ConvertFrom-Json
if ((Get-Prop $clusterObj 'status') -ne 'RUNNING' -or (Get-Prop $clusterObj 'health') -ne 'HEALTHY') {
  Fail ("Cluster not RUNNING/HEALTHY status={0} health={1}" -f (Get-Prop $clusterObj 'status'), (Get-Prop $clusterObj 'health'))
}
$ng = Invoke-External -FilePath 'yc' -ArgumentList @('managed-kubernetes', 'node-group', 'get', '--id', $nodeGroupId, '--format', 'json')
$ngObj = $ng.Text | ConvertFrom-Json
if ((Get-Prop $ngObj 'status') -ne 'RUNNING') { Fail ("Node group status={0}" -f (Get-Prop $ngObj 'status')) }
if ((Get-Prop $ngObj 'cluster_id') -ne $clusterId) { Fail 'Node group cluster_id does not match state cluster id' }
Write-Ok 'Cluster HEALTHY; node group RUNNING (IDs from state)'

function Get-LiveRulesFromYc {
  param([string]$SgId)
  # Positional ID form (yc rejects combining some flag styles inconsistently on PS)
  $res = Invoke-External -FilePath 'yc' -ArgumentList @('vpc', 'security-group', 'get', $SgId, '--format', 'json')
  $obj = $res.Text | ConvertFrom-Json
  $rawRules = Get-Prop $obj 'rules'
  $list = New-Object System.Collections.Generic.List[object]
  foreach ($r in @($rawRules)) {
    if ($null -eq $r) { continue }
    $ports = Get-Prop $r 'ports'
    $from = $null; $to = $null
    if ($null -ne $ports) {
      $from = ConvertTo-IntOrNull (Get-Prop $ports 'from_port')
      $to = ConvertTo-IntOrNull (Get-Prop $ports 'to_port')
      # YC often omits from_port when 0
      if ($null -eq $from -and $null -ne $to) { $from = 0 }
    }
    $cidrBlocks = Get-Prop $r 'cidr_blocks'
    $v4 = @()
    if ($null -ne $cidrBlocks) {
      $v4raw = Get-Prop $cidrBlocks 'v4_cidr_blocks'
      $v4 = @(ConvertTo-StringArray $v4raw)
    }
    $proto = Get-Prop $r 'protocol_name'
    if ([string]::IsNullOrWhiteSpace([string]$proto)) {
      Fail 'Live rule missing required protocol_name'
    }
    $dir = Get-Prop $r 'direction'
    if ([string]::IsNullOrWhiteSpace([string]$dir)) { Fail 'Live rule missing required direction' }
    $desc = Get-Prop $r 'description'
    if ($null -eq $desc) { $desc = '' }
    $rid = Get-Prop $r 'id'
    if ([string]::IsNullOrWhiteSpace([string]$rid)) { Fail 'Live rule missing required id' }

    [void]$list.Add([pscustomobject]@{
        Id               = [string]$rid
        Description      = [string]$desc
        Direction        = ([string]$dir).ToLowerInvariant()
        Protocol         = ([string]$proto).ToUpperInvariant()
        FromPort         = $from
        ToPort           = $to
        Cidrs            = @($v4 | ForEach-Object { $_.Trim() } | Sort-Object)
        PredefinedTarget = $(if ($null -eq (Get-Prop $r 'predefined_target') -or (Get-Prop $r 'predefined_target') -eq '') { $null } else { [string](Get-Prop $r 'predefined_target') })
        SecurityGroupId  = $(if ($null -eq (Get-Prop $r 'security_group_id') -or (Get-Prop $r 'security_group_id') -eq '') { $null } else { [string](Get-Prop $r 'security_group_id') })
      })
  }
  $rulesArr = @($list.ToArray())
  return [pscustomobject]@{
    Description = [string](Get-Prop $obj 'description')
    Rules       = $rulesArr
  }
}

Write-Step 'Load live SG rules (YC JSON)'
$masterLive = Get-LiveRulesFromYc -SgId $masterSgId
$nodesLive = Get-LiveRulesFromYc -SgId $nodesSgId
$allLive = @($masterLive.Rules) + @($nodesLive.Rules)
Write-Ok ("live_master_rules={0} live_nodes_rules={1}" -f @($masterLive.Rules).Count, @($nodesLive.Rules).Count)

if ($masterLive.Description -ne 'Managed Kubernetes master SG (credit-scoring)') {
  Write-Warn 'Master SG description differs from desired (cloud not mutated here)'
}
if ($nodesLive.Description -ne 'Managed Kubernetes nodes SG (credit-scoring)') {
  Write-Warn 'Nodes SG description differs from desired (cloud not mutated here)'
}

function Get-ExpectedPorts($Spec) {
  if ($null -ne $Spec.Port) { return @{ From = [int]$Spec.Port; To = [int]$Spec.Port } }
  if ($null -eq $Spec.FromPort -and $null -eq $Spec.ToPort) { return @{ From = $null; To = $null } }
  return @{ From = [int]$Spec.FromPort; To = [int]$Spec.ToPort }
}

function Test-RuleMatch($Live, $Spec, $SgIds) {
  $reasons = New-Object System.Collections.Generic.List[string]
  if ($Live.Description -ne $Spec.Description) { [void]$reasons.Add('description') }
  if ($Live.Direction -ne $Spec.Direction.ToLowerInvariant()) { [void]$reasons.Add('direction') }
  if ($Live.Protocol -ne $Spec.Protocol.ToUpperInvariant()) { [void]$reasons.Add('protocol') }

  $expPorts = Get-ExpectedPorts $Spec
  if ($null -eq $expPorts.From -and $null -eq $expPorts.To) {
    if ($null -ne $Live.FromPort -or $null -ne $Live.ToPort) { [void]$reasons.Add('ports(unexpected)') }
  } else {
    if ($Live.FromPort -ne $expPorts.From -or $Live.ToPort -ne $expPorts.To) { [void]$reasons.Add('ports') }
  }

  $expPre = $Spec.PredefinedTarget
  if ([string]::IsNullOrEmpty([string]$expPre)) { $expPre = $null }
  if ($Live.PredefinedTarget -ne $expPre) { [void]$reasons.Add('predefined_target') }

  if ($null -eq $Spec.PeerSg) {
    if ($null -ne $Live.SecurityGroupId) { [void]$reasons.Add('security_group_id(unexpected)') }
  } else {
    $want = $SgIds[$Spec.PeerSg]
    if ($Live.SecurityGroupId -ne $want) { [void]$reasons.Add('security_group_id') }
  }

  $expCidrs = @($Spec.Cidrs)
  if ($expCidrs -contains 'ADMIN') {
    # Admin CIDR(s): non-empty, not 0.0.0.0/0, prefix 1-32
    if (@($Live.Cidrs).Count -lt 1) { [void]$reasons.Add('cidrs(admin empty)') }
    foreach ($c in @($Live.Cidrs)) {
      if ($c -eq '0.0.0.0/0') { [void]$reasons.Add('cidrs(admin /0)') }
    }
  } else {
    $liveSorted = @($Live.Cidrs | Sort-Object)
    $expSorted = @($expCidrs | Sort-Object)
    if (($liveSorted -join ',') -ne ($expSorted -join ',')) { [void]$reasons.Add('cidrs') }
  }

  return [pscustomobject]@{ Ok = ($reasons.Count -eq 0); Reasons = ,$reasons.ToArray() }
}

Write-Step 'Exact-match 12 rules; forbid extras'
$sgIds = @{ master = $masterSgId; nodes = $nodesSgId }
$liveBySg = @{
  master = @($masterLive.Rules)
  nodes  = @($nodesLive.Rules)
}
$totalLive = @($liveBySg.master).Count + @($liveBySg.nodes).Count
if ($totalLive -ne 12) { Fail "Expected exactly 12 live rules across both SGs, found $totalLive" }

$importPlan = New-Object System.Collections.Generic.List[object]
$matchedIds = New-Object 'System.Collections.Generic.HashSet[string]'

foreach ($spec in $RuleCatalog) {
  $candidates = @($liveBySg[$spec.Sg] | Where-Object { $_.Description -eq $spec.Description })
  if ($candidates.Count -ne 1) {
    Fail ("Unique description match failed for {0}: count={1}" -f $spec.Address, $candidates.Count)
  }
  $live = $candidates[0]
  $m = Test-RuleMatch -Live $live -Spec $spec -SgIds $sgIds
  if (-not $m.Ok) {
    Fail ("Attribute mismatch for {0}: {1}" -f $spec.Address, ($m.Reasons -join ','))
  }
  if (-not $matchedIds.Add($live.Id)) { Fail "Duplicate live rule id matched" }
  $importId = '{0}:{1}' -f $sgIds[$spec.Sg], $live.Id
  [void]$importPlan.Add([pscustomobject]@{
      Address  = $spec.Address
      ImportId = $importId
      RuleId   = $live.Id
    })
}

# Forbid unmatched extras
foreach ($sgName in @('master', 'nodes')) {
  foreach ($lr in @($liveBySg[$sgName])) {
    if (-not $matchedIds.Contains($lr.Id)) {
      Fail ("Unknown extra live rule on {0} SG description='{1}'" -f $sgName, $lr.Description)
    }
  }
}
if ($importPlan.Count -ne 12) { Fail "Import plan size $($importPlan.Count) != 12" }
Write-Ok 'All 12 live rules matched; no extras'

# -------------------- Mandatory backup outside repo --------------------
Write-Step 'MANDATORY state backup to LOCALAPPDATA (UTF-8 no BOM)'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupFile = Join-Path $BackupDir "terraform-state-$stamp.json"
$shaFile = Join-Path $BackupDir "terraform-state-$stamp.sha256"

if ($DryRun) {
  # Still pull and validate backup mechanics without mutating state
  $pull = Invoke-External -FilePath 'terraform' -ArgumentList @('state', 'pull')
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($backupFile, $pull.Text, $utf8NoBom)
} else {
  $pull = Invoke-External -FilePath 'terraform' -ArgumentList @('state', 'pull')
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($backupFile, $pull.Text, $utf8NoBom)
}

if (-not (Test-Path -LiteralPath $backupFile) -or (Get-Item -LiteralPath $backupFile).Length -lt 100) {
  Fail "Backup missing/too small: $backupFile"
}
$backupText = [System.IO.File]::ReadAllText($backupFile)
try { $backupObj = $backupText | ConvertFrom-Json } catch { Fail "Backup JSON invalid: $_" }
$lineage = Get-Prop $backupObj 'lineage'
$serial = Get-Prop $backupObj 'serial'
if ([string]::IsNullOrWhiteSpace([string]$lineage)) { Fail 'Backup missing lineage' }
if ($null -eq $serial) { Fail 'Backup missing serial' }
$sha = (Get-FileHash -LiteralPath $backupFile -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText($shaFile, $sha, $utf8NoBom)
Write-Ok ("backup_ok serial={0} sha256={1}..." -f $serial, $sha.Substring(0, 12))

function Refresh-StateList {
  $r = Invoke-External -FilePath 'terraform' -ArgumentList @('state', 'list')
  $script:stateList = @(ConvertTo-StringArray ($r.Output | ForEach-Object { "$_".Trim() } | Where-Object { $_ }))
}

function Get-StateRuleIdStrict {
  param([string]$Address)
  if ($stateList -notcontains $Address) { return $null }
  # state show failure must not be treated as absence
  return (Get-StateAttrStrict -Address $Address -Attr 'id')
}

if ($DryRun) {
  Write-Ok 'DryRun complete: preflight + exact rule map + backup validated; no state mutation'
  Write-Host 'Next: re-run without -DryRun after operator approval.' -ForegroundColor Yellow
  exit 0
}

Write-Step 'Idempotent import loop'
$imported = 0; $skipped = 0; $repaired = 0
Refresh-StateList
foreach ($row in $importPlan) {
  Refresh-StateList
  $currentId = $null
  if ($stateList -contains $row.Address) {
    $currentId = Get-StateRuleIdStrict -Address $row.Address
  }

  if ($currentId -eq $row.RuleId) {
    Write-Ok "skip $($row.Address)"
    $skipped++
    continue
  }

  if ($null -ne $currentId -and $currentId -ne $row.RuleId) {
    Write-Warn "stale id on $($row.Address) — state rm"
    $rm = Invoke-External -FilePath 'terraform' -ArgumentList @('state', 'rm', $row.Address)
    $repaired++
  }

  Write-Step "import $($row.Address)"
  # Import ID format confirmed: security_group_id:rule_id
  $imp = Invoke-External -FilePath 'terraform' -ArgumentList @('import', $row.Address, $row.ImportId)
  $imported++
  Refresh-StateList
  $verify = Get-StateRuleIdStrict -Address $row.Address
  if ($verify -ne $row.RuleId) {
    Fail "Post-import State id must equal rule_id only; mismatch on $($row.Address)"
  }
}
Write-Ok "imported=$imported skipped=$skipped repaired_stale=$repaired"

Write-Step 'Post-migration state inventory'
Refresh-StateList
foreach ($addr in $ExpectedRuleAddresses) {
  if ($stateList -notcontains $addr) { Fail "Missing rule in state: $addr" }
}
# Accept 25 (baseline+12) or 26 if terraform_data.sg_rules_ready already tracked.
$okCounts = @(25, 26)
if ($okCounts -notcontains $stateList.Count) {
  Fail "Expected $ExpectedStateResourceCount state resources after migration (or 26 with sg_rules_ready), found $($stateList.Count)"
}
Write-Ok ("state_count={0}; all 12 rules present" -f $stateList.Count)

Write-Step 'Plan gate (terraform show -json); no-op only'
$planPath = Join-Path $BackupDir "post-migration-$stamp.tfplan"
$planJsonPath = Join-Path $BackupDir "post-migration-$stamp.plan.json"
Invoke-External -FilePath 'terraform' -ArgumentList @('plan', '-out', $planPath, '-no-color', '-input=false') | Out-Null
$show = Invoke-External -FilePath 'terraform' -ArgumentList @('show', '-json', $planPath)
[System.IO.File]::WriteAllText($planJsonPath, $show.Text, (New-Object System.Text.UTF8Encoding($false)))

$managed = New-Object System.Collections.Generic.List[string]
foreach ($a in $stateList) { [void]$managed.Add($a) }
foreach ($a in @($RuleCatalog | ForEach-Object { $_.Address })) {
  if (-not $managed.Contains($a)) { [void]$managed.Add($a) }
}
$changes = Get-PlanResourceChanges -PlanJsonText $show.Text
$gate = Test-PlanGateNoOp -ResourceChanges $changes -ManagedAddresses $managed.ToArray()
if (-not $gate.Ok) {
  Fail ("Plan gate blocked; non-no-op managed changes: {0}" -f ($gate.Violations -join '; '))
}
Write-Ok 'Plan gate PASS (no-op only for managed resources)'
Write-Host 'Apply is NOT run by this script. Separate explicit approval required if ever needed.' -ForegroundColor Yellow
exit 0
