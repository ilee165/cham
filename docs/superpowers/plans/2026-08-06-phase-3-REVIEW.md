---
phase: 03-wireguard-hybrid-dns
reviewed: 2026-08-06T15:16:41Z
depth: standard
status: issues
files_reviewed: 1
files_reviewed_list:
  - scripts/phase3-vm-watchdog.ps1
findings:
  critical: 1
  warning: 4
  info: 5
  total: 10
---

# Phase 3: Code Review Report

**Reviewed:** 2026-08-06T15:16:41Z
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues

## Summary

Reviewed `scripts/phase3-vm-watchdog.ps1` (cost-control watchdog that deallocates the three Phase 3 lab VMs at a deadline). The security posture is strong: user-supplied `-ResourceGroup` and `-VmNames` are validated against hard-coded allowlists and the hard-coded constants — not the user input — are passed to `az`, so there is no injection path into the CLI arguments; the deadline is strictly parsed as absolute UTC and bounded to 60 minutes; the official Azure CLI path is preferred over PATH lookup.

However, the script is correct only under PowerShell 7. It contains no `#Requires` guard, and under Windows PowerShell 5.1 — the default `powershell.exe` host on the operator's Windows machine — it demonstrably (empirically verified on 5.1.26100.8875) either crashes out of its retry loops on the first `az` stderr line, leaving VMs running, or spins forever unable to recognize the `deallocated` state. Several robustness gaps also undermine the script's own stated guarantees: the arm-time "auth probe" does not actually contact Azure, the retry loops are unbounded with no terminal failure signal, all `az` error output is discarded, and a failed log write can kill the watchdog mid-deallocation.

## Critical Issues

### CR-1: No PowerShell version guard — under Windows PowerShell 5.1 the watchdog crashes on az errors or loops forever, leaving VMs running

**File:** `scripts/phase3-vm-watchdog.ps1:1` (root cause), manifesting at lines 102, 142, 170, 175-184
**Issue:** The script has no `#Requires -Version` directive, yet it depends on PowerShell 7 semantics in two load-bearing places. On this Windows host both `powershell.exe` 5.1 and `pwsh` 7.3.6 are installed; if the watchdog is armed (interactively, via scheduled task, or via `Start-Process powershell`) under the default `powershell.exe`, two independent failure modes occur. Both were **empirically verified** on PowerShell 5.1.26100.8875 (and confirmed absent on pwsh 7.3.6):

1. **Stderr crash aborts the retry loops (lines 102, 142, 170).** Under PS 5.1, when a native command's stderr is redirected (`*> $null`, `2>$null`) while `$ErrorActionPreference = 'Stop'` (line 22), each stderr line is wrapped in an ErrorRecord and becomes a *terminating* error before the `$LASTEXITCODE` check is reached. Verified: `cmd /c "echo boom 1>&2" 2>$null` throws before the next statement on 5.1; reaches the exit-code check on 7.3.6. Consequence: the first failing `az vm deallocate` (line 142) — e.g. transient throttling or an expired token, exactly the cases the round-robin retry loop at lines 133-154 exists to survive — kills the entire watchdog. The VMs are left running with no watchdog armed, which is the precise cost-control failure this script exists to prevent.

2. **Verification loop never terminates (lines 175-184).** Under PS 5.1, `ConvertFrom-Json` does not enumerate a JSON array: `@($statusJson | ConvertFrom-Json)` yields a single-element array whose one element is the whole statuses array. `Where-Object { $_.code -like 'PowerState/*' }` then passes the *entire* inner array through (member enumeration makes `$_.code` an array, and `-like` on an array is truthy if any element matches), so line 180 produces a space-joined string such as `"ProvisioningState/succeeded PowerState/deallocated"`, the `^PowerState/` replace does not fire, the `'^[a-z]+$'` regex fails, and `$powerState` stays `'unknown'` forever. Verified: the exact pipeline from lines 175-184 yields `unknown` on 5.1 and `VM deallocated` on 7.3.6. Consequence: even after every VM successfully deallocates, the loop at lines 160-200 polls `az vm get-instance-view` every 15 seconds indefinitely and `watchdog_deallocation_verified=true` is never emitted.

**Fix:** Add a version guard as line 1 so the script fails loudly at arm time instead of malfunctioning at deadline:
```powershell
#Requires -Version 7.2
```
(7.2+ also guarantees redirected native stderr never honors `$ErrorActionPreference`.) Additionally, document/ensure the arming procedure invokes it via `pwsh -File`, never `powershell -File`. If Windows PowerShell 5.1 support is actually required, the native calls need localized `$ErrorActionPreference = 'Continue'` scopes and the JSON handling needs 5.1-safe enumeration — but the one-line guard is the correct minimal fix.

## Warnings

### WR-1: Arm-time "auth probe" does not contact Azure — an expired or revoked token passes the probe

**File:** `scripts/phase3-vm-watchdog.ps1:98-106`
**Issue:** The comment states "a broken/expired token must fail loudly at arm, not degrade into silent unknown-state polling at deadline," but `az account show` is a local operation: it reads the cached profile (`azureProfile.json`) and does not acquire or validate a token against Azure AD/ARM. It fails only when no account is logged in at all. An expired refresh token, revoked session, or conditional-access change passes the probe at arm time and then fails at deadline — degrading into exactly the polling behavior the comment claims to prevent (see WR-2).
**Fix:** Use a probe that forces real token acquisition, still read-only:
```powershell
& $azureCli account get-access-token --output none --only-show-errors *> $null
```
or a read-only ARM call scoped to the lab, which also validates RG visibility:
```powershell
& $azureCli group show --name $expectedResourceGroup --output none --only-show-errors *> $null
```

### WR-2: Both post-deadline loops retry indefinitely with no overall bound, terminal failure signal, or fatal-error detection

**File:** `scripts/phase3-vm-watchdog.ps1:133-154, 160-200`
**Issue:** The deallocate loop and the verification loop have no retry budget. If a VM was deleted, the RG was removed, the subscription context changed, or the token expired after arm (the 60-minute window exceeds nothing about token lifetime guarantees), the script spins forever at 15-second intervals, appending `deallocate_retry_pending` or `unknown` lines to the log without bound and never exiting — success (`watchdog_deallocation_verified=true`) and permanent failure are indistinguishable to anything supervising the process. Non-retryable errors (e.g. `ResourceNotFound`, `InvalidAuthenticationToken`) are retried identically to transient ones. The comment at lines 126-128 documents indefinite retry as intentional, but "indefinite with no escalation" means a wedged watchdog looks exactly like a working one.
**Fix:** Keep retries aggressive but bound them, and fail loudly and non-zero when the budget is exhausted:
```powershell
$retryBudget = $parsedDeadline.AddMinutes(30)
while ($pendingDeallocations.Count -gt 0) {
    if ([System.DateTimeOffset]::UtcNow -gt $retryBudget) {
        foreach ($vmName in $pendingDeallocations) {
            Write-PowerState -VmName $vmName -PowerState 'deallocate_FAILED_budget_exhausted'
        }
        throw 'Watchdog retry budget exhausted; manual deallocation required.'
    }
    # ... existing round-robin body ...
}
```
Apply the same bound to the verification loop (emit e.g. `watchdog_deallocation_UNVERIFIED` and exit non-zero).

### WR-3: All az stderr is discarded — retry causes are undiagnosable from the log

**File:** `scripts/phase3-vm-watchdog.ps1:102, 142, 170`
**Issue:** Every `az` invocation discards stderr (`*> $null`, `2>$null`). When a deallocation retries for 40 minutes, the log contains only repeated `deallocate_retry_pending` lines with zero indication of why (throttled? auth? VM gone? wrong subscription?). This also blocks any future fatal-vs-transient error triage (WR-2). For an unattended cost-control process, the error text is the single most valuable diagnostic and it is thrown away.
**Fix:** Capture stderr and record a sanitized first line in the log on failure:
```powershell
$azStderr = & $azureCli @deallocateArguments 2>&1 1>$null
if ($LASTEXITCODE -eq 0) {
    Write-PowerState -VmName $vmName -PowerState 'deallocate_accepted'
    $null = $pendingDeallocations.Remove($vmName)
}
else {
    $reason = (([string[]]$azStderr | Select-Object -First 1) -replace '\s+', ' ')
    Write-PowerState -VmName $vmName -PowerState ("deallocate_retry_pending reason={0}" -f $reason)
}
```

### WR-4: A failed log write kills the watchdog mid-deallocation

**File:** `scripts/phase3-vm-watchdog.ps1:72-84` (Add-Content at 83), interaction at 144-145
**Issue:** `Write-PowerState` calls `Add-Content` with `$ErrorActionPreference = 'Stop'` and no try/catch. Any transient log-file failure — antivirus scan holding the file, another process (a second armed watchdog instance uses the same default `$LogPath`, line 16) mid-append, disk full, path on a disconnected drive — throws a terminating error that aborts the entire deallocation loop. Nonessential telemetry can abort the essential cost-control operation. The ordering at lines 144-145 makes it worse: the log write happens *before* the VM is removed from `$pendingDeallocations`, so a log failure immediately after a successful deallocate kills the script while state still says the VM is pending.
**Fix:** Make logging best-effort and mutate state before logging:
```powershell
function Write-PowerState {
    param([Parameter(Mandatory)][string] $VmName,
          [Parameter(Mandatory)][string] $PowerState)
    $timestamp = [System.DateTimeOffset]::UtcNow.ToString('o')
    $line = '{0} vm={1} power_state={2}' -f $timestamp, $VmName, $PowerState
    try {
        Add-Content -LiteralPath $resolvedLogPath -Value $line -Encoding utf8
    }
    catch {
        Write-Warning ('watchdog log write failed: {0}' -f $_.Exception.Message)
    }
}
```
And at lines 143-145, remove from the pending set before calling `Write-PowerState`.

## Info

### IN-1: Case-handling mismatch between power-state regex and terminal comparison

**File:** `scripts/phase3-vm-watchdog.ps1:181, 192`
**Issue:** Line 181's `-match '^[a-z]+$'` is case-insensitive (verified: `'Deallocated' -match '^[a-z]+$'` is `$true`), but line 192's `-ceq 'VM deallocated'` is case-sensitive. If Azure ever returned `PowerState/Deallocated`, the state would pass the regex, log as `VM Deallocated`, yet never satisfy the `-ceq`, and the verification loop would never exit. Azure currently returns lowercase, so this is latent.
**Fix:** Normalize once — `$suffix = ([string] $powerStatus.code -replace '^PowerState/', '').ToLowerInvariant()` — or use `-cmatch` at line 181 so both checks agree.

### IN-2: Inconsistent case-sensitivity between the two allowlist validations

**File:** `scripts/phase3-vm-watchdog.ps1:33, 37-39`
**Issue:** The resource-group check uses case-sensitive `-cne` (rejecting `RG-CHAM-LAB`, even though Azure resource-group names are case-insensitive), while the VM-name check uses `Compare-Object` with its default case-insensitive comparison (accepting `VM-HUB-DDI`). Harmless in effect — downstream `az` calls use the hard-coded constants either way — but the asymmetric policy is surprising to operators.
**Fix:** Pick one policy: either `-ne` at line 33 (matches Azure semantics) or add `-CaseSensitive` to `Compare-Object` at line 38.

### IN-3: Whitespace-only VmNames tokens survive filtering and produce a misleading error

**File:** `scripts/phase3-vm-watchdog.ps1:26-31`
**Issue:** `RemoveEmptyEntries` runs before `Trim()`, so an input like `'vm-hub-ddi, ,vm-test-app,vm-test-mgmt'` yields an empty-string element, which then fails the count/difference check with the generic "must contain each approved Phase 3 VM exactly once" message rather than being cleanly dropped or clearly reported.
**Fix:** Filter after trimming: `... | ForEach-Object { $_.Trim() } | Where-Object { $_ }` (or, PS 7-only per CR-1, pass `[System.StringSplitOptions]'RemoveEmptyEntries,TrimEntries'` to `Split`).

### IN-4: Thread.Sleep blocks Ctrl+C for up to 15 seconds

**File:** `scripts/phase3-vm-watchdog.ps1:114, 152, 198`
**Issue:** `[System.Threading.Thread]::Sleep(15000)` blocks the pipeline thread; PowerShell cannot process Ctrl+C/StopProcessing until the .NET call returns, so operator abort of the retry loops can lag up to 15 seconds (250 ms in the deadline wait is negligible).
**Fix:** Use `Start-Sleep -Milliseconds 15000`, which is interruptible.

### IN-5: DryRun still requires the Azure CLI to be installed and still waits the full deadline

**File:** `scripts/phase3-vm-watchdog.ps1:86-96, 108-124`
**Issue:** CLI resolution (lines 86-96) runs before the DryRun branch, so `-DryRun` throws on a machine without `az` even though it makes no Azure call; and DryRun sits in the deadline wait loop (up to 60 minutes) before emitting `watchdog_dry_run_ok=true`. If DryRun is meant as a fast allowlist/argument validation, both behaviors are surprising and undocumented (the script has no comment-based help stating them).
**Fix:** Either emit the dry-run outputs immediately after validation (skipping the wait), or document in comment-based help that DryRun deliberately exercises the full timing path including CLI resolution.

---

_Reviewed: 2026-08-06T15:16:41Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
