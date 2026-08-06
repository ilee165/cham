---
phase: 03-wireguard-hybrid-dns
fixed_at: 2026-08-06T16:05:00Z
review_path: docs/superpowers/plans/2026-08-06-phase-3-REVIEW.md
iteration: 2
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-08-06T16:05:00Z (pass 2; pass 1 completed 2026-08-06T15:33:00Z)
**Source review:** docs/superpowers/plans/2026-08-06-phase-3-REVIEW.md
**Iteration:** 2
**File under fix:** `scripts/phase3-vm-watchdog.ps1`

**Summary:**
- Findings in scope (cumulative, both passes): 10
- Fixed: 10
- Skipped: 0
- Pass 1 (fix_scope: critical_warning): CR-1, WR-1..WR-4 — 5 fixed
- Pass 2 (fix_scope: info_only): IN-1..IN-5 — 5 fixed

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

## Out-of-Scope Findings in Pass 1 (Info — not attempted, fix_scope=critical_warning)

| ID | Title | Disposition |
|----|-------|-------------|
| IN-1 | Case-handling mismatch between power-state regex and terminal comparison | Skipped: Info severity, out of scope |
| IN-2 | Inconsistent case-sensitivity between the two allowlist validations | Skipped: Info severity, out of scope |
| IN-3 | Whitespace-only VmNames tokens survive filtering | Skipped: Info severity, out of scope |
| IN-4 | Thread.Sleep blocks Ctrl+C for up to 15 seconds | Skipped: Info severity, out of scope |
| IN-5 | DryRun still requires az and waits the full deadline | Skipped: Info severity, out of scope |

All five Info findings were subsequently fixed in pass 2 (below).

## Fixed Issues — Pass 2 (Info, fix_scope=info_only)

### IN-1: Case-handling mismatch between power-state regex and terminal comparison

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `83d10e4` — "Normalize power-state casing so shape check and terminal compare agree"
**Applied fix:** Normalized once per the review's primary suggestion — `$suffix` is now `(-replace '^PowerState/', '').ToLowerInvariant()` — and the shape check was tightened to `-cmatch '^[a-z]+$'` so both it and the `-ceq 'VM deallocated'` terminal comparison agree by construction, even if Azure ever returns `PowerState/Deallocated`.
**Verification:** PS parser (`[Parser]::ParseFile`) zero errors.

### IN-2: Inconsistent case-sensitivity between the two allowlist validations

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `50a797d` — "Make the resource-group allowlist check case-insensitive to match Azure semantics"
**Applied fix:** Changed the resource-group check from `-cne` to `-ne` (the review's first option), making both allowlist validations uniformly case-insensitive and matching Azure's own name semantics. Added a comment noting that downstream `az` calls use the hard-coded constants regardless, so casing never reaches the CLI arguments.
**Verification:** PS parser zero errors; end-to-end smoke test passed `-ResourceGroup RG-CHAM-LAB` and it was accepted.

### IN-3: Whitespace-only VmNames tokens survive filtering

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `1cbadd3` — "Trim VmNames tokens before dropping empty entries"
**Applied fix:** Replaced the split-then-trim pipeline with `[System.StringSplitOptions] 'RemoveEmptyEntries, TrimEntries'` (the review's PS 7-only option, now safe under the pass-1 `#Requires -Version 7.2` guard). TrimEntries runs before empty-entry removal, so whitespace-only tokens are dropped cleanly instead of failing the count check with a misleading message.
**Verification:** PS parser zero errors; empirically confirmed `'vm-hub-ddi, ,vm-test-app,vm-test-mgmt'` yields exactly the 3 clean tokens; the same input was used in the end-to-end smoke test.

### IN-4: Thread.Sleep blocks Ctrl+C for up to 15 seconds

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `bc3eb90` — "Replace Thread.Sleep with interruptible Start-Sleep in all wait loops"
**Applied fix:** All three `[System.Threading.Thread]::Sleep` sites (deadline wait, deallocate retry loop, verification loop) now use interruptible `Start-Sleep -Milliseconds`, so Ctrl+C/StopProcessing is honored promptly. The deadline wait keeps its existing 250 ms slice computation.
**Verification:** PS parser zero errors; grep confirms zero `Thread]::Sleep` occurrences remain.

### IN-5: DryRun still requires az and waits the full deadline

**Files modified:** `scripts/phase3-vm-watchdog.ps1`
**Commit:** `242d249` — "Short-circuit -DryRun before CLI resolution and the deadline wait"
**Applied fix:** Took the review's first option: the `-DryRun` branch now short-circuits immediately after argument/allowlist validation and log setup — before CLI resolution, the auth probe, and the deadline wait — so it needs no Azure CLI installed, makes no Azure call, and returns immediately. The pass-1 output contract is preserved exactly: three `DryRunNoMutation` log lines plus `watchdog_dry_run_ok=true` and `watchdog_vm_allowlist_ok=true` on stdout, documented in a comment at the block. The pass-1 `if (-not $DryRun)` guard on the auth probe was left in place as defense in depth.
**Verification:** PS parser zero errors; end-to-end `-DryRun` run with a deadline 50 minutes out completed in 853 ms with exit 0 and the full log/stdout contract — proving the wait is skipped.

## Verification Summary

- After every fix (both passes): `[System.Management.Automation.Language.Parser]::ParseFile(...)` under `pwsh -NoProfile` — zero parse errors each time.
- WR-3 idiom validated empirically before application (see adaptation note above).
- Pass-1 end-to-end smoke test: `-DryRun` with a 3-second deadline and valid allowlist arguments — emitted `watchdog_dry_run_ok=true` and `watchdog_vm_allowlist_ok=true`, wrote three `DryRunNoMutation` log lines, exited cleanly. No Azure calls made; no VM mutation possible in this test path.
- Pass-2 end-to-end smoke test (after all five Info fixes): `-DryRun` with a deadline 50 minutes out, `-ResourceGroup RG-CHAM-LAB` (uppercase), and `-VmNames 'vm-hub-ddi, ,VM-TEST-APP,vm-test-mgmt'` (whitespace-only token, mixed case) — exit 0 in 853 ms, both ok markers on stdout, exactly three `DryRunNoMutation` log lines. Exercises IN-2, IN-3, and IN-5 end to end; no Azure calls made.
- Pass-2 commits fast-forwarded onto `main` (`421d6d8..242d249`) via the isolated-worktree cleanup; working tree left clean apart from this report.

---

_Fixed: 2026-08-06T16:05:00Z (pass 2)_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
