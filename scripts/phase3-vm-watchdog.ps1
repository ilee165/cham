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

    # CR-05: resource-group and VM names are not globally unique, so every az
    # call must be pinned to the lab subscription rather than riding whatever
    # default context the CLI happens to hold. A GUID (not a subscription
    # name) is required: names resolve through the same ambient profile this
    # parameter exists to bypass.
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')]
    [string] $SubscriptionId,

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
    # CR-05: the subscription is part of the audit trail — a log line that
    # cannot say WHERE a deallocation landed cannot prove it landed in the lab.
    $line = '{0} vm={1} subscription={2} power_state={3}' -f
        $timestamp, $VmName, $SubscriptionId, $PowerState
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

# CR-05: every az invocation the watchdog can ever issue is built by exactly
# one of these three functions, each pinning `--subscription`. -DryRun prints
# what they return and the live path splats what they return, so the printed
# argument vectors ARE the executed ones — not a parallel copy that can drift.
function Get-AuthProbeArguments {
    @(
        'account', 'get-access-token',
        '--subscription', $SubscriptionId,
        '--output', 'none',
        '--only-show-errors'
    )
}

function Get-DeallocateArguments {
    param(
        [Parameter(Mandatory)]
        [string] $VmName
    )

    @(
        'vm', 'deallocate',
        '--resource-group', $expectedResourceGroup,
        '--name', $VmName,
        '--subscription', $SubscriptionId,
        '--no-wait',
        '--only-show-errors'
    )
}

function Get-InstanceViewArguments {
    param(
        [Parameter(Mandatory)]
        [string] $VmName
    )

    @(
        'vm', 'get-instance-view',
        '--resource-group', $expectedResourceGroup,
        '--name', $VmName,
        '--subscription', $SubscriptionId,
        '--query', 'instanceView.statuses',
        '--output', 'json',
        '--only-show-errors'
    )
}

# -DryRun is a fast argument/allowlist validation: it short-circuits here,
# before CLI resolution, the auth probe, and the deadline wait, so it needs
# no Azure CLI installed, makes no Azure call, and returns immediately.
# Output contract (relied on by verification and by
# ddi-reconciler/tests/test_watchdog_args.py): one DryRunNoMutation log line
# per approved VM, one `watchdog_planned_az_argv:` stdout line per az
# invocation the live path would issue, then the two ok markers on stdout.
if ($DryRun) {
    foreach ($vmName in $expectedVmNames) {
        Write-PowerState -VmName $vmName -PowerState 'DryRunNoMutation'
    }
    Write-Output ('watchdog_planned_az_argv: az {0}' -f (
        (Get-AuthProbeArguments) -join ' '
    ))
    foreach ($vmName in $expectedVmNames) {
        Write-Output ('watchdog_planned_az_argv: az {0}' -f (
            (Get-DeallocateArguments -VmName $vmName) -join ' '
        ))
        Write-Output ('watchdog_planned_az_argv: az {0}' -f (
            (Get-InstanceViewArguments -VmName $vmName) -join ' '
        ))
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
# acquisition against Azure AD while remaining read-only. Because the probe
# carries `--subscription` (CR-05), it also proves at arm time that the pinned
# subscription is reachable from this login — an unreachable or mistyped
# subscription fails here, not silently at deadline.
# Skipped in -DryRun, which must make no Azure call.
if (-not $DryRun) {
    $probeArguments = Get-AuthProbeArguments
    $probeOutput = @(& $azureCli @probeArguments 2>&1)
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

# CR-06: `az vm deallocate --no-wait` exits 0 when Azure ACCEPTS the
# long-running operation, not when the VM reaches `deallocated`. The original
# design removed a VM from its request set on acceptance and left a separate
# later loop that only polled — so an accepted operation that subsequently
# failed or stalled left the cost-bearing VM running until the budget threw.
# Request and verification are therefore one per-VM state machine:
#
#   pending-request --accepted--> pending-verify --'VM deallocated'--> done
#          ^                            |
#          +-- any state other than deallocating/deallocated persisting
#              past the stall window (reissue) --------------------------+
#
# 'VM deallocating' waits without reissue (the operation is demonstrably in
# progress); everything else — running, stopped, unknown — is treated as a
# dead acceptance once the stall window passes. Reissuing is safe: the
# operation set stays deallocate-only, and deallocate on an already
# deallocating or deallocated VM is idempotent at the Azure API.
#
# Round-robin: every non-done VM is attempted each cycle so one persistently
# failing VM cannot starve the others. Retries stay aggressive but bounded:
# 30 minutes past the deadline the watchdog fails loudly and exits non-zero,
# so a wedged run is distinguishable from a working one.
$retryBudget = $parsedDeadline.AddMinutes(30)
# ~12 poll cycles at 15 s — long enough that a healthy deallocation has
# always reported PowerState/deallocating, short enough to leave several
# reissue rounds inside the 30-minute budget.
$stallReissueAfter = [System.TimeSpan]::FromMinutes(3)

$vmStates = @{}
foreach ($vmName in $expectedVmNames) {
    $vmStates[$vmName] = [pscustomobject]@{
        Phase         = 'pending-request'
        AcceptedAtUtc = [System.DateTimeOffset]::MinValue
        # WD-02: acceptance LATCHES. A VM reissued back to pending-request
        # after a stalled acceptance is not the same, at budget exhaustion,
        # as one whose deallocate Azure never accepted: the former may have
        # a deallocation in flight whose outcome was never verified, and the
        # audit trail must say so.
        EverAccepted  = $false
    }
}

while ($true) {
    $pendingVmNames = @(
        $expectedVmNames | Where-Object { $vmStates[$_].Phase -ne 'done' }
    )
    if ($pendingVmNames.Count -eq 0) {
        break
    }

    if ([System.DateTimeOffset]::UtcNow -gt $retryBudget) {
        $anyUnverified = $false
        foreach ($vmName in $pendingVmNames) {
            # Classify by acceptance history, not by current phase alone: a
            # VM reissued back to pending-request after a stalled acceptance
            # still has an unverified deallocation on the record.
            if (
                $vmStates[$vmName].Phase -eq 'pending-request' -and
                -not $vmStates[$vmName].EverAccepted
            ) {
                Write-PowerState -VmName $vmName -PowerState 'deallocate_FAILED_budget_exhausted'
            }
            else {
                $anyUnverified = $true
                Write-PowerState -VmName $vmName -PowerState 'verify_FAILED_budget_exhausted'
            }
        }
        if ($anyUnverified) {
            Write-Output 'watchdog_deallocation_UNVERIFIED=true'
        }
        throw 'Watchdog retry budget exhausted; manual deallocation and verification required.'
    }

    foreach ($vmName in $pendingVmNames) {
        $state = $vmStates[$vmName]

        if ($state.Phase -eq 'pending-request') {
            $deallocateArguments = Get-DeallocateArguments -VmName $vmName
            $deallocateOutput = @(& $azureCli @deallocateArguments 2>&1)
            if ($LASTEXITCODE -eq 0) {
                # State first, telemetry second: a logging hiccup right after
                # a successful request must not leave the phase stale.
                # Acceptance is NOT completion — only an instance view showing
                # 'VM deallocated' retires the VM from this machine.
                $state.Phase = 'pending-verify'
                $state.AcceptedAtUtc = [System.DateTimeOffset]::UtcNow
                $state.EverAccepted = $true
                Write-PowerState -VmName $vmName -PowerState 'deallocate_accepted'
            }
            else {
                Write-PowerState -VmName $vmName -PowerState (
                    'deallocate_retry_pending reason={0}' -f (
                        Get-FirstStderrLine -NativeOutput $deallocateOutput
                    )
                )
            }
            continue
        }

        # Phase: pending-verify.
        $statusArguments = Get-InstanceViewArguments -VmName $vmName
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
            $state.Phase = 'done'
        }
        elseif (
            $powerState -cne 'VM deallocating' -and
            ([System.DateTimeOffset]::UtcNow - $state.AcceptedAtUtc) -gt $stallReissueAfter
        ) {
            # The acceptance went stale: the VM is not deallocated and not
            # observably deallocating well past the stall window. Fall back
            # to pending-request so next cycle reissues the deallocate.
            $state.Phase = 'pending-request'
            Write-PowerState -VmName $vmName -PowerState (
                'deallocate_reissued last_power_state={0}' -f $powerState
            )
        }
    }

    $stillPending = @(
        $expectedVmNames | Where-Object { $vmStates[$_].Phase -ne 'done' }
    )
    if ($stillPending.Count -gt 0) {
        Start-Sleep -Milliseconds 15000
    }
}

Write-Output 'watchdog_deallocation_verified=true'
