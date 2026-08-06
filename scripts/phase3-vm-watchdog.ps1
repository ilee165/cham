#Requires -Version 7.2
# PowerShell 7.2+ is mandatory. Under Windows PowerShell 5.1, redirected
# native stderr becomes a terminating error while $ErrorActionPreference is
# 'Stop' (aborting the retry loops on the first az stderr line), and
# ConvertFrom-Json does not enumerate JSON arrays (wedging verification in
# the 'unknown' state forever). Arm via `pwsh -File`, never `powershell -File`.
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string] $DeadlineUtc,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string] $ResourceGroup,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string] $VmNames,

    [ValidateNotNullOrEmpty()]
    [string] $LogPath = (Join-Path ([System.IO.Path]::GetTempPath()) 'cham-phase3-vm-watchdog.log'),

    [switch] $DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$expectedResourceGroup = 'rg-cham-lab'
$expectedVmNames = @('vm-hub-ddi', 'vm-test-app', 'vm-test-mgmt')
$requestedVmNames = @(
    $VmNames.Split(
        ',',
        [System.StringSplitOptions]::RemoveEmptyEntries
    ) | ForEach-Object { $_.Trim() }
)

if ($ResourceGroup -cne $expectedResourceGroup) {
    throw "ResourceGroup must be $expectedResourceGroup."
}

$vmNameDifference = @(
    Compare-Object -ReferenceObject $expectedVmNames -DifferenceObject $requestedVmNames
)
if (
    $requestedVmNames.Count -ne $expectedVmNames.Count -or
    $vmNameDifference.Count -ne 0
) {
    throw 'VmNames must contain each approved Phase 3 VM exactly once.'
}

$parsedDeadline = [System.DateTimeOffset]::MinValue
$parsed = [System.DateTimeOffset]::TryParse(
    $DeadlineUtc,
    [System.Globalization.CultureInfo]::InvariantCulture,
    [System.Globalization.DateTimeStyles]::RoundtripKind,
    [ref] $parsedDeadline
)
if (-not $parsed -or $parsedDeadline.Offset -ne [System.TimeSpan]::Zero) {
    throw 'DeadlineUtc must be an absolute ISO-8601 UTC timestamp.'
}

$nowUtc = [System.DateTimeOffset]::UtcNow
if ($parsedDeadline -le $nowUtc) {
    throw 'DeadlineUtc must be in the future.'
}
if (($parsedDeadline - $nowUtc) -gt [System.TimeSpan]::FromMinutes(60)) {
    throw 'DeadlineUtc cannot exceed the approved 60-minute window.'
}

$resolvedLogPath = [System.IO.Path]::GetFullPath($LogPath)
$logDirectory = [System.IO.Path]::GetDirectoryName($resolvedLogPath)
if (-not [string]::IsNullOrWhiteSpace($logDirectory)) {
    $null = New-Item -ItemType Directory -Path $logDirectory -Force
}

function Write-PowerState {
    param(
        [Parameter(Mandatory)]
        [string] $VmName,

        [Parameter(Mandatory)]
        [string] $PowerState
    )

    $timestamp = [System.DateTimeOffset]::UtcNow.ToString('o')
    $line = '{0} vm={1} power_state={2}' -f $timestamp, $VmName, $PowerState
    Add-Content -LiteralPath $resolvedLogPath -Value $line -Encoding utf8
}

$officialAzureCli = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
if (Test-Path -LiteralPath $officialAzureCli -PathType Leaf) {
    $azureCli = $officialAzureCli
}
else {
    $azureCommand = Get-Command az.cmd -ErrorAction SilentlyContinue
    if ($null -eq $azureCommand) {
        throw 'Azure CLI was not found.'
    }
    $azureCli = $azureCommand.Source
}

# Arm-time read-only authentication probe: a broken/expired token must fail
# loudly at arm, not degrade into silent unknown-state polling at deadline.
# `account show` only reads the cached local profile and cannot detect an
# expired or revoked token; `account get-access-token` forces a real token
# acquisition against Azure AD while remaining read-only.
# Skipped in -DryRun, which must make no Azure call.
if (-not $DryRun) {
    & $azureCli account get-access-token --output none --only-show-errors *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Azure CLI authentication probe failed at arm time.'
    }
}

while ([System.DateTimeOffset]::UtcNow -lt $parsedDeadline) {
    $remaining = $parsedDeadline - [System.DateTimeOffset]::UtcNow
    $sleepMilliseconds = [Math]::Min(
        250,
        [Math]::Max(1, [Math]::Ceiling($remaining.TotalMilliseconds))
    )
    [System.Threading.Thread]::Sleep([int] $sleepMilliseconds)
}

if ($DryRun) {
    foreach ($vmName in $expectedVmNames) {
        Write-PowerState -VmName $vmName -PowerState 'DryRunNoMutation'
    }
    Write-Output 'watchdog_dry_run_ok=true'
    Write-Output 'watchdog_vm_allowlist_ok=true'
    return
}

# Round-robin: attempt every pending VM each cycle so one persistently
# failing VM cannot starve deallocation requests for the others. Retries
# remain indefinite; the operation set stays deallocate-only.
$pendingDeallocations = [System.Collections.Generic.HashSet[string]]::new(
    [string[]] $expectedVmNames,
    [System.StringComparer]::Ordinal
)
while ($pendingDeallocations.Count -gt 0) {
    foreach ($vmName in @($pendingDeallocations)) {
        $deallocateArguments = @(
            'vm', 'deallocate',
            '--resource-group', $expectedResourceGroup,
            '--name', $vmName,
            '--no-wait',
            '--only-show-errors'
        )
        & $azureCli @deallocateArguments *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-PowerState -VmName $vmName -PowerState 'deallocate_accepted'
            $null = $pendingDeallocations.Remove($vmName)
        }
        else {
            Write-PowerState -VmName $vmName -PowerState 'deallocate_retry_pending'
        }
    }
    if ($pendingDeallocations.Count -gt 0) {
        [System.Threading.Thread]::Sleep(15000)
    }
}

$pendingVmNames = [System.Collections.Generic.HashSet[string]]::new(
    [string[]] $expectedVmNames,
    [System.StringComparer]::Ordinal
)
while ($pendingVmNames.Count -gt 0) {
    foreach ($vmName in @($pendingVmNames)) {
        $statusArguments = @(
            'vm', 'get-instance-view',
            '--resource-group', $expectedResourceGroup,
            '--name', $vmName,
            '--query', 'instanceView.statuses',
            '--output', 'json',
            '--only-show-errors'
        )
        $statusJson = @(& $azureCli @statusArguments 2>$null) -join [Environment]::NewLine

        $powerState = 'unknown'
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($statusJson)) {
            try {
                $statuses = @($statusJson | ConvertFrom-Json)
                $powerStatus = $statuses |
                    Where-Object { $_.code -like 'PowerState/*' } |
                    Select-Object -First 1
                if ($null -ne $powerStatus) {
                    $suffix = [string] $powerStatus.code -replace '^PowerState/', ''
                    if ($suffix -match '^[a-z]+$') {
                        $powerState = 'VM ' + $suffix
                    }
                }
            }
            catch {
                $powerState = 'unknown'
            }
        }

        Write-PowerState -VmName $vmName -PowerState $powerState
        if ($powerState -ceq 'VM deallocated') {
            $null = $pendingVmNames.Remove($vmName)
        }
    }

    if ($pendingVmNames.Count -gt 0) {
        [System.Threading.Thread]::Sleep(15000)
    }
}

Write-Output 'watchdog_deallocation_verified=true'
