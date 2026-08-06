---
phase: 03-wireguard-hybrid-dns
fixed_at: 2026-08-06T15:33:00Z
review_path: docs/superpowers/plans/2026-08-06-phase-3-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-08-06T15:33:00Z
**Source review:** docs/superpowers/plans/2026-08-06-phase-3-REVIEW.md
**Iteration:** 1
**File under fix:** `scripts/phase3-vm-watchdog.ps1`

**Summary:**
- Findings in scope (fix_scope: critical_warning): 5
- Fixed: 5
- Skipped: 0
- Out of scope (Info, not attempted): 5

## Fixed Issues

### CR-1: No PowerShell version guard — 5.1 crashes the retry loops or wedges verification

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `55aab77` — "Require PowerShell 7.2 in the Phase 3 watchdog"
**Applied fix:** Added `#Requires -Version 7.2` as line 1 (per the review's suggested minimal fix) plus a comment block documenting the two 5.1 failure modes (stderr-as-terminating-error under `$ErrorActionPreference = 'Stop'`; `ConvertFrom-Json` non-enumeration of JSON arrays) and instructing that arming must use `pwsh -File`, never `powershell -File`.
**Verification:** PS parser (`[Parser]::ParseFile`) zero errors; final end-to-end `-DryRun` run under pwsh 7 succeeded with the guard in place.

### WR-1: Arm-time "auth probe" did not contact Azure

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `af7d185` — "Make the arm-time auth probe force real token acquisition"
**Applied fix:** Replaced `az account show` (local profile read) with `az account get-access-token --output none --only-show-errors` (the review's first suggested option), which forces real token acquisition against Azure AD while remaining read-only. Comment updated to explain why. Still skipped under `-DryRun`.
**Verification:** PS parser zero errors.

### WR-2: Unbounded retry loops with no terminal failure signal

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `ef70e8c` — "Bound watchdog retry loops with a 30-minute post-deadline budget"
**Applied fix:** Added shared `$retryBudget = $parsedDeadline.AddMinutes(30)`. The deallocate loop now logs `deallocate_FAILED_budget_exhausted` per pending VM and throws on exhaustion; the verification loop logs `verify_FAILED_budget_exhausted` per pending VM, emits `watchdog_deallocation_UNVERIFIED=true`, and throws (uncaught throw under `pwsh -File` exits non-zero). Updated the "retries remain indefinite" comment to describe the bounded policy.
**Verification:** PS parser zero errors.

### WR-3: All az stderr discarded — retry causes undiagnosable

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `380f7ae` — "Record az stderr reasons instead of discarding all error output"
**Applied fix (adapted from review suggestion):** All three cited sites (auth probe, `vm deallocate`, `vm get-instance-view`) now capture the merged `2>&1` stream. A new `Get-FirstStderrLine` helper filters `ErrorRecord` objects and returns the whitespace-collapsed first stderr line, logged as `reason={...}` on retry (`deallocate_retry_pending reason=...`, `unknown reason=...`) and included in the arm-time probe's throw message. The `get-instance-view` JSON is rebuilt from non-ErrorRecord (stdout) items only, so parsing is unaffected.
**Adaptation note:** The review's suggested idiom `$azStderr = & az ... 2>&1 1>$null` was empirically tested under pwsh 7 and captures **nothing** (the merged stream is discarded with stream 1). The ErrorRecord-filtering approach was verified to capture stderr correctly under `Set-StrictMode -Version Latest` + `$ErrorActionPreference = 'Stop'`.
**Verification:** PS parser zero errors; helper smoke test under StrictMode confirmed: mixed stdout/stderr yields first stderr line whitespace-collapsed, empty input yields empty string, stdout-only join preserves output for JSON parsing.

### WR-4: A failed log write kills the watchdog mid-deallocation

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `643943d` — "Make watchdog log writes best-effort and update state before logging"
**Applied fix:** Wrapped `Add-Content` in `Write-PowerState` with try/catch and a `Write-Warning` fallback (per the review's suggested function body), and reordered the deallocate success branch so the VM is removed from `$pendingDeallocations` *before* `Write-PowerState` runs — telemetry can no longer strand state.
**Verification:** PS parser zero errors; final end-to-end `-DryRun` run exercised `Write-PowerState` successfully (three `DryRunNoMutation` log lines written).

## Out-of-Scope Findings (Info — not attempted, fix_scope=critical_warning)

| ID | Title | Disposition |
|----|-------|-------------|
| IN-1 | Case-handling mismatch between power-state regex and terminal comparison | Skipped: Info severity, out of scope |
| IN-2 | Inconsistent case-sensitivity between the two allowlist validations | Skipped: Info severity, out of scope |
| IN-3 | Whitespace-only VmNames tokens survive filtering | Skipped: Info severity, out of scope |
| IN-4 | Thread.Sleep blocks Ctrl+C for up to 15 seconds | Skipped: Info severity, out of scope |
| IN-5 | DryRun still requires az and waits the full deadline | Skipped: Info severity, out of scope |

## Verification Summary

- After every fix: `[System.Management.Automation.Language.Parser]::ParseFile(...)` under `pwsh -NoProfile` — zero parse errors each time.
- WR-3 idiom validated empirically before application (see adaptation note above).
- Final end-to-end smoke test: `-DryRun` with a 3-second deadline and valid allowlist arguments — emitted `watchdog_dry_run_ok=true` and `watchdog_vm_allowlist_ok=true`, wrote three `DryRunNoMutation` log lines, exited cleanly. No Azure calls made; no VM mutation possible in this test path.

---

_Fixed: 2026-08-06T15:33:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
