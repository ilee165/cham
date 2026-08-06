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
# TrimEntries runs before empty-entry removal, so whitespace-only tokens
# (e.g. 'vm-a, ,vm-b') are dropped cleanly instead of surviving as empty
# strings and failing the count check below with a misleading message.
# TrimEntries needs .NET 5+, guaranteed by the #Requires -Version 7.2 guard.
$requestedVmNames = @(
    $VmNames.Split(
        ',',
        [System.StringSplitOptions] 'RemoveEmptyEntries, TrimEntries'
    )
)

# Allowlist checks are uniformly case-insensitive, matching Azure's own
# name semantics; downstream az calls use the hard-coded constants
# regardless, so casing never reaches the CLI arguments.
if ($ResourceGroup -ne $expectedResourceGroup) {
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
    # Logging is best-effort telemetry: a transient log-write failure
    # (antivirus hold, concurrent writer, disk full) must never abort the
    # essential deallocation work.
    try {
        Add-Content -LiteralPath $resolvedLogPath -Value $line -Encoding utf8
    }
    catch {
        Write-Warning ('watchdog log write failed: {0}' -f $_.Exception.Message)
    }
}

# Native az stderr captured via 2>&1 arrives as ErrorRecord objects mixed
# into the success stream; the first stderr line, whitespace-collapsed, is
# the retry diagnostic recorded in the log.
function Get-FirstStderrLine {
    param(
        [object[]] $NativeOutput
    )

    $firstLine = [string[]] @(
        $NativeOutput |
            Where-Object { $_ -is [System.Management.Automation.ErrorRecord] }
    ) | Select-Object -First 1
    ([string] $firstLine -replace '\s+', ' ').Trim()
}

# -DryRun is a fast argument/allowlist validation: it short-circuits here,
# before CLI resolution, the auth probe, and the deadline wait, so it needs
# no Azure CLI installed, makes no Azure call, and returns immediately.
# Output contract (relied on by verification): one DryRunNoMutation log
# line per approved VM, then the two ok markers on stdout.
if ($DryRun) {
    foreach ($vmName in $expectedVmNames) {
        Write-PowerState -VmName $vmName -PowerState 'DryRunNoMutation'
    }
    Write-Output 'watchdog_dry_run_ok=true'
    Write-Output 'watchdog_vm_allowlist_ok=true'
    return
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
    $probeOutput = @(& $azureCli account get-access-token --output none --only-show-errors 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw (
            'Azure CLI authentication probe failed at arm time: {0}' -f (
                Get-FirstStderrLine -NativeOutput $probeOutput
            )
        )
    }
}

while ([System.DateTimeOffset]::UtcNow -lt $parsedDeadline) {
    $remaining = $parsedDeadline - [System.DateTimeOffset]::UtcNow
    $sleepMilliseconds = [Math]::Min(
        250,
        [Math]::Max(1, [Math]::Ceiling($remaining.TotalMilliseconds))
    )
    # Start-Sleep (not Thread.Sleep) so Ctrl+C can interrupt the wait.
    Start-Sleep -Milliseconds ([int] $sleepMilliseconds)
}

# Round-robin: attempt every pending VM each cycle so one persistently
# failing VM cannot starve deallocation requests for the others. Retries
# stay aggressive but are bounded: 30 minutes past the deadline the
# watchdog fails loudly and exits non-zero, so a wedged run is
# distinguishable from a working one. The operation set stays
# deallocate-only.
$retryBudget = $parsedDeadline.AddMinutes(30)
$pendingDeallocations = [System.Collections.Generic.HashSet[string]]::new(
    [string[]] $expectedVmNames,
    [System.StringComparer]::Ordinal
)
while ($pendingDeallocations.Count -gt 0) {
    if ([System.DateTimeOffset]::UtcNow -gt $retryBudget) {
        foreach ($vmName in $pendingDeallocations) {
            Write-PowerState -VmName $vmName -PowerState 'deallocate_FAILED_budget_exhausted'
        }
        throw 'Watchdog retry budget exhausted; manual deallocation required.'
    }
    foreach ($vmName in @($pendingDeallocations)) {
        $deallocateArguments = @(
            'vm', 'deallocate',
            '--resource-group', $expectedResourceGroup,
            '--name', $vmName,
            '--no-wait',
            '--only-show-errors'
        )
        $deallocateOutput = @(& $azureCli @deallocateArguments 2>&1)
        if ($LASTEXITCODE -eq 0) {
            # State first, telemetry second: a logging hiccup right after a
            # successful deallocate must not leave the VM marked pending.
            $null = $pendingDeallocations.Remove($vmName)
            Write-PowerState -VmName $vmName -PowerState 'deallocate_accepted'
        }
        else {
            Write-PowerState -VmName $vmName -PowerState (
                'deallocate_retry_pending reason={0}' -f (
                    Get-FirstStderrLine -NativeOutput $deallocateOutput
                )
            )
        }
    }
    if ($pendingDeallocations.Count -gt 0) {
        Start-Sleep -Milliseconds 15000
    }
}

$pendingVmNames = [System.Collections.Generic.HashSet[string]]::new(
    [string[]] $expectedVmNames,
    [System.StringComparer]::Ordinal
)
while ($pendingVmNames.Count -gt 0) {
    if ([System.DateTimeOffset]::UtcNow -gt $retryBudget) {
        foreach ($vmName in $pendingVmNames) {
            Write-PowerState -VmName $vmName -PowerState 'verify_FAILED_budget_exhausted'
        }
        Write-Output 'watchdog_deallocation_UNVERIFIED=true'
        throw 'Watchdog verification budget exhausted; manual verification required.'
    }
    foreach ($vmName in @($pendingVmNames)) {
        $statusArguments = @(
            'vm', 'get-instance-view',
            '--resource-group', $expectedResourceGroup,
            '--name', $vmName,
            '--query', 'instanceView.statuses',
            '--output', 'json',
            '--only-show-errors'
        )
        $statusOutput = @(& $azureCli @statusArguments 2>&1)
        $statusJson = @(
            $statusOutput |
                Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] }
        ) -join [Environment]::NewLine

        $powerState = 'unknown'
        if ($LASTEXITCODE -ne 0) {
            $powerState = 'unknown reason={0}' -f (
                Get-FirstStderrLine -NativeOutput $statusOutput
            )
        }
        elseif (-not [string]::IsNullOrWhiteSpace($statusJson)) {
            try {
                $statuses = @($statusJson | ConvertFrom-Json)
                $powerStatus = $statuses |
                    Where-Object { $_.code -like 'PowerState/*' } |
                    Select-Object -First 1
                if ($null -ne $powerStatus) {
                    # Normalize casing once so this shape check and the
                    # case-sensitive 'VM deallocated' comparison below can
                    # never disagree (e.g. a future 'PowerState/Deallocated').
                    $suffix = ([string] $powerStatus.code -replace '^PowerState/', '').ToLowerInvariant()
                    if ($suffix -cmatch '^[a-z]+$') {
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
        Start-Sleep -Milliseconds 15000
    }
}

Write-Output 'watchdog_deallocation_verified=true'
