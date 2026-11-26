# Quick synthetic tests for Plan Gate (PowerShell 5.1 / StrictMode).
# Does not touch cloud or Terraform state.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$here = $PSScriptRoot
. (Join-Path $here 'SgPlanGate.ps1')

$managed = @(
  'module.network.yandex_vpc_security_group_rule.master_from_nodes',
  'module.kubernetes.yandex_kubernetes_cluster.this'
)

function Assert-True([bool]$Cond, [string]$Name) {
  if (-not $Cond) { throw "ASSERT FAIL: $Name" }
  Write-Host "[PASS] $Name" -ForegroundColor Green
}

# 1) no-op only / empty changes
$r = Test-PlanGateNoOp -ResourceChanges ([object[]]@()) -ManagedAddresses $managed
Assert-True $r.Ok 'empty resource_changes is OK'

$jsonNoop = @'
{"resource_changes":[{"address":"module.network.yandex_vpc_security_group_rule.master_from_nodes","change":{"actions":["no-op"]}}]}
'@
$changes = Get-PlanResourceChanges -PlanJsonText $jsonNoop
$r = Test-PlanGateNoOp -ResourceChanges $changes -ManagedAddresses $managed
Assert-True $r.Ok 'explicit no-op is OK'

# 2) create
$jsonCreate = '{"resource_changes":[{"address":"module.network.yandex_vpc_security_group_rule.master_from_nodes","change":{"actions":["create"]}}]}'
$r = Test-PlanGateNoOp -ResourceChanges (Get-PlanResourceChanges $jsonCreate) -ManagedAddresses $managed
Assert-True (-not $r.Ok) 'create is blocked'

# 3) update
$jsonUpdate = '{"resource_changes":[{"address":"module.kubernetes.yandex_kubernetes_cluster.this","change":{"actions":["update"]}}]}'
$r = Test-PlanGateNoOp -ResourceChanges (Get-PlanResourceChanges $jsonUpdate) -ManagedAddresses $managed
Assert-True (-not $r.Ok) 'update is blocked'

# 4) delete
$jsonDelete = '{"resource_changes":[{"address":"module.network.yandex_vpc_security_group_rule.master_from_nodes","change":{"actions":["delete"]}}]}'
$r = Test-PlanGateNoOp -ResourceChanges (Get-PlanResourceChanges $jsonDelete) -ManagedAddresses $managed
Assert-True (-not $r.Ok) 'delete is blocked'

# 5) replace
$jsonReplace = '{"resource_changes":[{"address":"module.kubernetes.yandex_kubernetes_cluster.this","change":{"actions":["delete","create"]}}]}'
$r = Test-PlanGateNoOp -ResourceChanges (Get-PlanResourceChanges $jsonReplace) -ManagedAddresses $managed
Assert-True (-not $r.Ok) 'replace is blocked'

# 6) malformed JSON
$malformedOk = $false
try {
  $null = Get-PlanResourceChanges -PlanJsonText '{not-json'
} catch {
  $malformedOk = $true
}
Assert-True $malformedOk 'malformed JSON throws'

# unmanaged address with create should not block
$jsonOther = '{"resource_changes":[{"address":"module.other.thing","change":{"actions":["create"]}}]}'
$r = Test-PlanGateNoOp -ResourceChanges (Get-PlanResourceChanges $jsonOther) -ManagedAddresses $managed
Assert-True $r.Ok 'unmanaged create ignored'

Write-Host 'Test-SgPlanGate: ALL PASS' -ForegroundColor Green
exit 0
