# Shared Plan Gate helpers for Invoke-SgStateMigration.ps1 and unit tests.
# Compatible with Windows PowerShell 5.1 + StrictMode.

Set-StrictMode -Version Latest

function ConvertTo-StringArray {
  param([AllowNull()]$Value)
  $list = New-Object System.Collections.Generic.List[string]
  if ($null -eq $Value) {
    return [string[]]@()
  }
  if ($Value -is [string]) {
    [void]$list.Add($Value)
    return [string[]]@($list.ToArray())
  }
  foreach ($item in @($Value)) {
    if ($null -ne $item -and $item -isnot [System.Array]) {
      [void]$list.Add([string]$item)
    }
    elseif ($null -ne $item -and $item -is [System.Array]) {
      foreach ($inner in @($item)) {
        if ($null -ne $inner) { [void]$list.Add([string]$inner) }
      }
    }
  }
  return [string[]]@($list.ToArray())
}

function Get-PlanResourceChanges {
  param(
    [Parameter(Mandatory = $true)]
    [string]$PlanJsonText
  )
  if ([string]::IsNullOrWhiteSpace($PlanJsonText)) {
    throw 'Plan JSON is empty'
  }
  try {
    $obj = $PlanJsonText | ConvertFrom-Json
  } catch {
    throw "Malformed plan JSON: $($_.Exception.Message)"
  }
  if ($null -eq $obj) { throw 'Malformed plan JSON: null root' }

  $list = New-Object System.Collections.Generic.List[object]
  if (@($obj.PSObject.Properties.Name) -contains 'resource_changes' -and $null -ne $obj.resource_changes) {
    foreach ($rc in @($obj.resource_changes)) {
      if ($null -ne $rc) { [void]$list.Add($rc) }
    }
  }
  return [object[]]@($list.ToArray())
}

function Test-PlanGateNoOp {
  <#
    .SYNOPSIS
      Require no-op for managed addresses. Any create/update/delete/replace blocks.
  #>
  param(
    [Parameter(Mandatory = $false)]
    [AllowEmptyCollection()]
    [AllowNull()]
    [object[]]$ResourceChanges = @(),
    [Parameter(Mandatory = $true)]
    [AllowEmptyCollection()]
    [string[]]$ManagedAddresses
  )

  $managed = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
  foreach ($a in @(ConvertTo-StringArray $ManagedAddresses)) {
    if (-not [string]::IsNullOrWhiteSpace($a)) { [void]$managed.Add($a) }
  }

  $violations = New-Object System.Collections.Generic.List[string]
  foreach ($rc in @($ResourceChanges)) {
    if ($null -eq $rc) { continue }
    if ($rc -is [string] -or $rc -is [ValueType]) { continue }

    $names = @($rc.PSObject.Properties.Name)
    if ($names -notcontains 'address') { continue }
    $addr = [string]$rc.address
    if (-not $managed.Contains($addr)) { continue }

    if ($names -notcontains 'change' -or $null -eq $rc.change) {
      [void]$violations.Add("$addr missing change object")
      continue
    }
    $changeNames = @($rc.change.PSObject.Properties.Name)
    if ($changeNames -notcontains 'actions' -or $null -eq $rc.change.actions) {
      [void]$violations.Add("$addr missing change.actions")
      continue
    }

    $actionItems = @(ConvertTo-StringArray $rc.change.actions)
    $bad = New-Object System.Collections.Generic.List[string]
    foreach ($a in $actionItems) {
      $al = ([string]$a).ToLowerInvariant()
      if ($al -ne 'no-op') { [void]$bad.Add($al) }
    }
    if ($bad.Count -gt 0) {
      [void]$violations.Add(("{0} actions=[{1}]" -f $addr, ($bad.ToArray() -join ',')))
    }
  }

  $violArr = [string[]]@($violations.ToArray())
  return [pscustomobject]@{
    Ok         = ($violArr.Count -eq 0)
    Violations = $violArr
  }
}
