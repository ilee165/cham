---
phase: 3
target: PR #2 (feat/phase-3-wireguard-hybrid-dns → main)
reviewers: [opencode, codex]
reviewed_at: 2026-08-06T14:00:00Z
reviewed_commit: 97c39ec (post test-script removal; graphify-out removal 08a9514 landed after review start)
unavailable: [gemini (account tier unsupported), cursor (agent CLI not installed), ollama (server unreachable), claude (self — excluded for independence), qwen/coderabbit (not installed)]
scope_note: Reviewers were instructed not to propose a test file for scripts/phase3-vm-watchdog.ps1 (operator declined) and to skip graphify-out contents.
---

# Cross-AI Review — PR #2 (Phase 3: WireGuard tunnel + hybrid DNS)

## OpenCode Review

# Cross-AI Review — PR #2 (Phase 3: WireGuard tunnel + hybrid DNS)

## 1. Summary

This PR is documentation and evidence for an already-executed, operator-approved cost window plus one deallocation-only PowerShell safety helper. The material is unusually consistent: plan, verification record, research, Checkpoint A/B/C/D evidence, runbook, and `.continue-here.md` cross-reference the same commits, hashes, timestamps, addresses, and boolean results, and the claim that Phase 3's exit criteria are met is directly supported by matching evidence rows. Sanitization is disciplined — no public/home IPs, subscription/tenant IDs, key material, MACs, or raw command output appear, and only RFC1918 ranges, internal hostnames, and Azure constants (`168.63.129.16`) are shown. The watchdog is genuinely deallocation-only with a hard allow-list and is the strongest code artifact. The remaining issues are robustness gaps in the watchdog's unbounded retry loops, a couple of evidence-clarity items, and minor documentation nits — none of which undermine the safety story or the exit-criteria claim.

## 2. Strengths

- **Watchdog is correctly scoped and hardened.** `scripts/phase3-vm-watchdog.ps1` contains only `vm deallocate` and `vm get-instance-view` calls; it cannot start, resize, deploy, or apply. Resource group is validated case-sensitively against exactly `rg-cham-lab`, the VM set is compared against the three expected names (duplicates/extra names rejected), and the deadline must be an absolute ISO-8601 UTC timestamp (`Offset == Zero`), in the future, and ≤ 60 minutes away.
- **Deallocation is *verified*, not assumed.** The script uses `--no-wait` deallocate followed by instance-view polling that only removes a VM from the pending set on the exact `PowerState/deallocated` code; it retries reads and never treats a successful command exit as proof.
- **Safe failure direction.** `-DryRun` writes `DryRunNoMutation` for all three VMs and makes no Azure call; output is suppressed on mutation commands; logs contain only timestamps, VM names, and power states.
- **The key-install procedure is genuinely idempotent and key-safe.** The marker-aware script creates/reuses `hub.key` only when `REPLACE_ON_HOST` is present, otherwise compares stored vs. configured keys and hard-stops on mismatch; the private value is stdin-fed, never in arguments or output, and no implicit rotation path exists.
- **Evidence and plan are mutually consistent.** Watchdog deadline (`05:03:59Z` = arm + exactly 60 min), lease hostname (`phase3-lease-20260806041731` ↔ trigger `04:17:31Z`), approved watchdog SHA-256, Checkpoint B bound commit, destroy plan hash (`900e7179…f43785`), "36 to destroy / 36 to add", and the 0/0/0/0 post-destroy sweep all line up across files.
- **The plan's corrections are real and reflected in evidence.** The hub-only gate explicitly excludes `vm-test-app.azure.dwsolution.co` (moved to post-start), `cut -f2` handshake extraction avoids the PowerShell/awk quoting hazard, direct-hop-before-composed ordering is enforced, and management VM start count is literally zero in the verification record.
- **Closeout is unconditional and correctly ordered** (tunnel down → containers stopped → deallocate all → verify from instance view → cancel watchdog last), and the destroy used an approved saved plan with hash re-verification — no raw `terraform destroy` or `-auto-approve`.
- **Honest operational documentation.** The deviations section (Windows `-i` path, `ProxyCommand` for the jump hop, `known_hosts` remediation) and the research doc's note that `graphify-out` was absent and GSD files were missing make the process reproducible.

## 3. Concerns

- **MEDIUM — Watchdog deallocate and poll loops are unbounded.** The `do/until` retry on failed `vm deallocate` and the confirmation poll loop both run forever with no max-attempt, time cap, or escalation. If the Azure CLI is unauthenticated/broken at deadline, or a VM never reports a `PowerState/*` status (e.g., a failed/provisioning state), the script logs `unknown` forever and never emits the final `watchdog_deallocation_verified=true` marker. The behavior fails safe (it only keeps retrying a monotone operation), but the "independent backstop" can silently hang while the operator believes it is working — and a supervisor would never get a signal distinguishing "still retrying" from "stuck."
- **MEDIUM — Deallocate acceptance is never logged.** On success, no `deallocate accepted` event is written; the log only shows poll outcomes. Combined with the retry loop, the log cannot tell a reader that deallocation was issued and the poll is the only open question.
- **LOW — `-DryRun` blocks until the deadline before doing anything.** The wait loop runs before the dry-run branch, so a far-future deadline makes the dry run hang for hours. The one-second deadline used in the evidence works, but it is a footgun for future operators; behavior should be documented or the wait skipped in dry-run.
- **LOW — The "operator-active setup under ten minutes" claim is asserted, not demonstrated.** The only committed timestamps bracket arm `04:03:59Z` → lease trigger `04:17:31Z`, i.e., 13.5 minutes of wall clock. The assertion is plausible (the span includes VM boot, cloud-init, key work, and tunnel gates) but the metric is undefined and the evidence doesn't record the measured operator-active interval.
- **LOW — Deadline-time `az` authentication is assumed.** An expired/broken Azure CLI token at deadline would surface as the unbounded `unknown` polling loop above rather than an early, loud failure. Worth an at-arm-time read-only auth probe or explicit operator note.
- **LOW — `graphify-out/` generated artifacts inflate this docs/evidence PR.** This matches the AGENTS.md convention, but they should be regenerated/confirmed at merge time so the graph matches the merged tree rather than the branch snapshot.
- **LOW — Checkov "15 skipped" is undocumented.** The count is reproducible across plan-verification and closeout evidence (38/0/15), but nothing records which checks are suppressed or why, so the number isn't auditable.
- **LOW — Two cosmetic doc inconsistencies.** The architecture mermaid diagram labels the app node with the spoke subnet CIDR (`vm-test-app 10.10.4.0/22`) while the hub node shows a host IP (`BIND9 10.10.0.10`); the resolution table and evidence use `10.10.4.20`. Also, the plan header still reads "Awaiting operator review" despite Checkpoint A evidence (same date) showing it was executed and Checkpoint B later being authorized — the status line was never updated post-approval.

## 4. Suggestions

- **Watchdog (no tests, respecting scope):** Bound the retry/poll loops — e.g., after N consecutive failures or M minutes past deadline, write a distinct final marker (`watchdog_unverified=true`) and exit nonzero — or at minimum emit a periodic `STILL_PENDING` heartbeat and log `deallocate_accepted` for each VM so a stuck state is distinguishable in the log.
- **Watchdog:** Perform a read-only auth/state probe at arm time (e.g., `az vm list` or `az account show`) so a token problem is caught before the deadline instead of at it; the current evidence validates behavior but not this failure mode.
- **Evidence:** Replace the "under ten minutes" assertion with the concrete measured operator-active interval (or state what the two committed timestamps exclude) so the claim is checkable from the committed record.
- **Docs:** Update the plan header status post-approval, align the mermaid app label to `10.10.4.20`, and add one line noting the checkov skip basis (or verify suppressions are intentional).
- **Housekeeping:** Regenerate/refresh `graphify-out/` to match merged HEAD, or drop it from this PR, to avoid shipping a stale graph with a docs-only change.

## 5. Risk Assessment

**LOW.** The lab is already destroyed; this PR ships documentation plus a deallocation-only helper, so there is no compute-cost or security exposure in the change itself. The exit criteria are supported by matching, internally consistent evidence, and the cost-control story (hub-first sequencing, watchdog backstop, unconditional closeout, approved saved destroy plan) is sound. Residual risk is limited to watchdog robustness (unbounded retry/poll loops and deadline-time auth assumption) that could mask a failed backstop on a *future* rerun, plus minor evidence-clarity and doc-consistency items — none of which affect the validity of the Phase 3 completion claim or introduce a sanitization leak.

---

## Codex Review

## Summary

The PR credibly demonstrates that Phase 3’s core tunnel, bidirectional DNS, bounded-cost execution, closeout, and approved destroy criteria were met. Sanitization is strong, and no secret or identifier leak is apparent. I would request changes before merge because the watchdog has a partial-failure weakness and several plan/evidence statements remain internally inconsistent.

## Strengths

- Explicit approval, commit/hash binding, five-minute pre-start guards, hub-first sequencing, and a 60-minute deadline provide strong cost controls.
- Evidence covers recent handshakes, bidirectional transfer, split tunneling, exact-address DNS publishing, UDP/TCP resolution in both directions, app auto-registration, and fresh DHCP/DDNS propagation.
- Closeout verifies power states from Azure instance view, cancels the watchdog last, and records Private Resolver as disabled and absent.
- Destroy evidence ties the action to an approved saved-plan hash and verifies 36 resources destroyed, empty lab state, retained bootstrap storage, and no recreation apply.
- The watchdog passed parser validation and dry-run; its only Azure operations are `deallocate` and `get-instance-view`.
- Evidence consistently omits public/home IPs, subscription/tenant IDs, key material, and raw command/state output. No apparent sanitization leak was found.

## Concerns

- **MEDIUM — Watchdog retries can starve later VMs.** In `scripts/phase3-vm-watchdog.ps1:116-132`, each VM is retried indefinitely before the script advances to the next. A persistent VM-specific failure for `vm-hub-ddi` would prevent any deallocation request from reaching the app or management VM.
- **MEDIUM — The under-ten-minute claim is unsupported.** `checkpoint-c-closeout.md` gives `04:03:59Z` and `04:17:31Z`, an elapsed interval of 13 minutes 32 seconds, then claims setup was under ten minutes. The plan explicitly requires timestamps proving that criterion.
- **MEDIUM — The plan retains commands known to have failed live.** The plan still uses `ssh.exe ... -J` for app access, while the evidence and runbook state that `-J` did not carry the required identity to the jump host and an explicit `ProxyCommand` was necessary.
- **LOW — Fresh-lease chronology is not recorded as explicitly as required.** Checkpoint B records absence before the trigger, successful renewal, and subsequent record presence, but omits the plan’s narrow assertions that the lease issue time and DDNS creation were after the trigger.
- **LOW — The plan status is stale.** It still says “Awaiting operator review” and “No Phase 3 implementation…authorized,” while the rest of the PR marks Phase 3 executed, complete, and destroyed.

## Suggestions

- Change the watchdog to attempt every pending VM once per retry cycle, so one failure cannot block requests for the others. Preserve indefinite retries, the fixed allow-list, and deallocation-only behavior; then repeat the existing parser, source-scan, and dry-run checks.
- Correct the timing evidence to 13:32 wall-clock, or add sanitized operator-active interval totals that genuinely demonstrate less than ten minutes. Do not rerun the destroyed lab solely for this.
- Replace all `ssh -J` examples with the exact sanitized `ProxyCommand` form proven during Checkpoint B, including one copy-pasteable runbook example.
- Add only two boolean evidence rows: `lease_issue_after_trigger=true` and `ddns_created_after_trigger=true`; no raw lease or DNS output is needed.
- Add a short execution-history banner to the plan while retaining its original pre-execution authorization language as historical context.

## Risk Assessment

**MEDIUM.** There is no current cloud-cost exposure because the lab was successfully destroyed, and the substantive Phase 3 acceptance evidence is convincing. Remaining risk is primarily future operational safety: the watchdog can fail to address all VMs under partial failure, and known-broken SSH instructions could waste a future bounded compute window.

---

## Consensus Summary

Two independent reviewers (OpenCode, Codex) with full-diff context. Overall
verdicts diverge — OpenCode LOW risk, Codex MEDIUM (would request changes) —
but their findings overlap heavily.

### Agreed Strengths (both reviewers)

- Cost/authorization controls are strong and consistently enforced: explicit
  approval bound to commit + watchdog hash, five-minute pre-start guards,
  hub-first sequencing, 60-minute deadline, closeout verified from instance
  view, destroy tied to an approved saved-plan hash.
- Sanitization is disciplined; neither reviewer found a secret or identifier
  leak anywhere in the diff.
- Plan, evidence, runbook, and `.continue-here.md` are internally consistent
  (commits, hashes, timestamps, addresses, booleans cross-check).
- The watchdog is genuinely deallocation-only with a hard VM allow-list.

### Agreed Concerns (both reviewers — highest priority)

1. **Watchdog retry/poll loop robustness (MEDIUM × 2).** The per-VM
   `do/until` deallocate retry and the confirmation poll are unbounded.
   Codex: a persistent failure on the first VM starves deallocation requests
   for the remaining VMs. OpenCode: an unauthenticated/broken `az` at
   deadline degrades to silent infinite `unknown` polling, indistinguishable
   from progress. Suggested fix (no test file, per scope): attempt every
   pending VM each retry cycle, log `deallocate_accepted`, emit a heartbeat
   or bounded `watchdog_unverified` marker, and probe `az` auth at arm time.
2. **"Under ten minutes" operator-active claim (MEDIUM/LOW).** Committed
   timestamps bracket 13m32s of wall clock; the sub-ten-minute assertion is
   not demonstrated by the committed record. Fix: record the measured
   operator-active interval or state what the bracket excludes.
3. **Stale plan status lines (LOW × 2).** The plan header still reads
   "Awaiting operator review" / "No Phase 3 implementation authorized" while
   the PR documents execution and destroy. Fix: add an execution-history
   banner, keep original authorization text as history.

### Divergent / Single-Reviewer Findings

- **Codex MEDIUM:** the plan retains `ssh.exe -J` examples that the evidence
  itself records as failing live (identity not carried to the jump hop);
  runbook has the corrected `ProxyCommand` form but the plan was not updated.
- **Codex LOW:** fresh-lease evidence omits explicit
  `lease_issue_after_trigger` / `ddns_created_after_trigger` booleans the
  plan requires.
- **OpenCode LOW:** `-DryRun` waits for the full deadline before branching
  (footgun for future operators); checkov's 15 skipped checks are
  unexplained; mermaid app-node label shows the spoke CIDR where the
  resolution table uses the host address.
- **Moot:** both-era comments on `graphify-out/` artifacts — removed from
  the branch in `08a9514` after the review snapshot.
