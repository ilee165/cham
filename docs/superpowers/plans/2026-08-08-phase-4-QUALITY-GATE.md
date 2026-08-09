---
phase: 04-cloudflare-reconciler-v2
reviewed: 2026-08-08T23:20:00Z
review_depth: deep
scope_base: 7337b297421ef1e4d62aaaffaf74672a1fd7077d
scope_head: b898a39a674d138edc38b5d992d68c53089499d5
changed_files: 50
source_files_reviewed: 32
grade:
  score: 62
  letter: D-
  gate: fail
  phase_5_recommendation: no_go
findings:
  critical_code: 4
  warning_code: 3
  blocking_documentation_and_plan_gaps: 9
status: issues_found
---

# Phase 4 Quality Gate and Grade Report

## Verdict

**Grade: 62/100 (D-)**  
**Quality gate: FAIL**  
**Phase 5 recommendation: NO-GO for implementation or automation.**

Phase 4 has a strong architectural skeleton, broad tests, clean infrastructure validation,
and good baseline secret/ownership controls. It is not safe to close, however. Four
independently reproduced defects remain in the reconciler's destructive or convergence
paths. Two can turn incomplete/malformed Spatium truth into an authorized delete, one can
overwrite an Azure auto-registered record in a race while reporting success, and one makes
Cloudflare proxy-mode tampering impossible to heal.

The documentation also records an end-to-end split-horizon demonstration that its own
evidence says was never run, and the current Phase 5 plan is stale enough to produce
non-initializing Cloudflare jobs and regress the read-only drift-token boundary.

Phase 5 planning and remediation may proceed. Do not enable unattended reconciliation,
execute the current Phase 5 workflow plan, or treat Phase 4 as formally complete until the
exit conditions in this report pass.

The complete GSD finding detail and reproductions are in
[2026-08-08-phase-4-final-REVIEW.md](2026-08-08-phase-4-final-REVIEW.md).

## Grade Breakdown

| Dimension | Score | Assessment |
|---|---:|---|
| Functional design and integration | 17/20 | Packaging, CLI modes, provider isolation, snapshot contract, edge filtering, and exit codes are coherently wired. |
| Correctness and data safety | 7/25 | Four Critical failures affect deletion safety, Azure ownership, and Cloudflare convergence. Any one is a release blocker. |
| Tests and reproducibility | 16/20 | 305 tests pass offline and on Python 3.11, but the suite misses all four Critical paths; the packaged entry point and Ruff gate are not covered in normal CI. |
| Infrastructure and security controls | 14/15 | Terraform validation, TFLint, Checkov, secret scanning, state separation, scoped ownership, and current read-only drift access are strong. |
| Documentation, evidence, and handoff | 5/15 | Evidence is useful but completion claims, runbook commands, ADR scope, and the Phase 5 executable plan contradict live behavior. |
| Maintainability and repository tooling | 3/5 | Ruff is absent from the declared dev environment and the local graph is 65 commits stale. |
| **Total** | **62/100** | **D-; gate failed** |

The score is not an average of passing commands. A DNS reconciler with proven
delete/clobber paths cannot receive a passing gate regardless of happy-path coverage.

## Critical Code Findings

### CR-01 — Overlapping Spatium pages can certify incomplete truth

**Location:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:274-327`

The pagination check rejects only a page identical to the immediately previous page and
compares the declared total to the raw item count. For pages `A,B` and `B,C` with
`total=4`, duplicate `B` fills the count while record `D` never arrives. The adapter returns
`A,B,C` with `read_verified=True`; the runner can then authorize `DELETE D`.

This scenario was reproduced independently. Track immutable identity across the complete
walk, reject overlap, and compare the unique identity count to a stable declared total.
Add a runner-level regression proving deletion remains blocked.

### CR-02 — Wrong-typed Spatium fields are dropped from verified truth

**Location:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:383-408`

Required fields are converted with `str()` before validation. JSON `null` for
`record_type` becomes `"NONE"`, is treated as unsupported, and is silently skipped after
the collection was already certified complete. With other valid desired records present,
the empty-truth guard does not help and the omitted managed record becomes a delete.

This scenario was reproduced independently. Validate required field types and nonempty
values before normalization. Only skip a well-formed, genuinely unsupported record type.

### CR-03 — Azure auto-registration can be clobbered between list and write

**Location:** `ddi-reconciler/src/ddi_reconciler/providers/azure.py:75-123,190-200`

The provider records ownership during its initial list and then issues unconditional
`create_or_update` and `delete` calls. If Azure auto-registration creates a record at a
managed key after the list but before the write, the cached guard remains clear. The
reconciler overwrites the record, re-fetches its own value, and reports convergence.

This race was reproduced independently. Preserve ETags and use create-only/If-Missing and
If-Not-Modified preconditions for adds, updates, and deletes. On a precondition failure,
re-fetch, re-plan, and refuse a now-auto-registered key.

### CR-04 — Cloudflare proxy-mode tamper cannot be healed

**Location:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:69,321-377,393-436`

Create requests establish `proxied: false`, but reads discard `proxied` and updates never
send it. A managed record changed to proxied mode has Cloudflare Auto TTL (`1`). The
reconciler PATCHes only the desired TTL, leaves proxy mode enabled, re-fetches TTL `1`, and
raises `ConvergenceError`. If desired TTL is Auto, proxy drift can be invisible.

This scenario was reproduced independently. Model DNS-only proxy policy, compare it, and
PATCH `proxied:false` with the desired content/TTL; the post-apply read must prove it.

## Code Warnings

| ID | Location | Issue | Required action |
|---|---|---|---|
| WR-01 | `.github/workflows/drift.yml:50-65` | Exit codes other than `1` are treated as successful completion unless exactly `2`; shell/tool failures can leave the schedule green and silent. | Accept only `0` and `2`; fail closed on every other status and test `0/1/2/unexpected`. |
| WR-02 | `terraform/modules/hub/main.tf:92,113`; `cloud-init.yml.tpl:36-37,63-64` | The module exposes configurable spoke CIDRs but DNS, HTTP, BIND ACL, and NAT paths retain hard-coded `10.10.0.0/16`. | Derive all related rules from one input and plan-test a non-default CIDR. |
| WR-03 | `ddi-reconciler/pyproject.toml:22-25` | `uv sync --dev` does not install Ruff, so the documented `uv run ruff check .` gate fails with “program not found.” | Add a compatible pinned Ruff dev dependency, update the lock, and run it in CI. |

Additional non-blocking test gaps:

- `.github/workflows/reconciler-tests.yml:62-70` prints `truth_verified` but does not fail
  when it is false.
- `tests/test_cli.py:176-182` exercises module invocation rather than the installed
  `cham-reconcile` console script.
- The current workflow empties cloud credentials but does not itself prevent arbitrary
  outbound network calls. The suite passed with outbound HTTP(S) forced to a dead proxy,
  which verifies present behavior but not future enforcement.

## Documentation and Phase Handoff Findings

### DOC-B01 — The checked end-to-end demo was not performed

`README.md:58,61-67` and the Phase 4 plan at `:1965,2006` claim completion. The same plan
at `:1935,1949-1963` and `docs/evidence/phase4/split-horizon.txt:51-100` state that no
laptop-over-tunnel run occurred and that the hub resolver returns the public answer.
`curl --resolve` bypassed DNS, and the local Spatium check required port 1053.

Either perform and capture the real DNS-plus-HTTP tunnel path, or uncheck/redefine the
criterion and describe the narrower local-resolver proof honestly.

### DOC-B02 — The runbook still instructs the non-working path

`docs/runbook.md:148-152` says bringing up WireGuard and flushing DNS makes the same URL
internal. Cloud-init leaves a placeholder private key and disables WireGuard
(`terraform/modules/hub/cloud-init.yml.tpl:17-23,101-105`), and the evidence confirms it
was disabled. The runbook also references an install script that is not tracked.

### DOC-B03 — ADR-006 and operations disagree on snapshot scope/lifecycle

`docs/decisions.md:64-70` documents an unfiltered two-edge nightly command and requires
each session to end with an export. The live workflow is intentionally public-only
(`.github/workflows/drift.yml:7-17,51-52`), and `docs/runbook.md:114-125` has no export,
review, dry-run/apply, or snapshot-commit procedure.

### DOC-B04 — The Phase 5 plan is not rebased onto reviewed workflows

The plan expects PR-created saved plans, merge-triggered apply, and one-step destroy at
`:340-353`. Live workflows use credential-free PR checks, manually dispatched current-main
saved plans, separately supplied run/SHA/hash inputs for apply, and two-stage destroy.
The plan must be rewritten around the reviewed exact-artifact model before execution.

### DOC-B05 — Proposed Cloudflare CI is incomplete and cannot initialize

Phase 5 plan `:163-212` calls bare `terraform init`, references an apply plan it never
downloads, and omits artifact manifest/hash/commit verification. The Cloudflare root uses
a partial AzureRM backend (`terraform/cloudflare/main.tf:24-31`) whose storage account,
subscription, and tenant are intentionally supplied out of band. Mirror the existing
Azure backend discovery and complete saved-plan trust chain in both Cloudflare jobs.

### DOC-B06 — The Phase 5 plan regresses least privilege

Current scheduled drift uses repository secret `CLOUDFLARE_API_TOKEN_RO` and no Azure/OIDC
permission. The Phase 5 plan provisions and passes the edit-capable
`CLOUDFLARE_API_TOKEN`. Preserve a repository-level read-only token for unattended reads
and keep edit capability only in the protected apply environment.

### DOC-B07 — Known deferrals are neither fully disclosed nor scheduled

README says exactly two items were deferred to Phase 5, while the Phase 4 plan also records
the Spatium apex zone shadowing Microsoft 365 discovery and a malformed truth-side CNAME.
The Phase 5 plan schedules none of these, nor ADR-007/tunnel/resolver unification. Assign
them to explicit Phase 5 tasks or a named backlog.

### DOC-B08 — Stale unchecked implementation snippets are unsafe to follow

The Phase 4 plan retains 35 unchecked A/B steps while the unperformed C3 step is checked.
Stale Terraform examples conflict with live NSG priorities, omit
`allow_overwrite = false`, and use bare `terraform apply`. Mark implemented deviations or
superseded instructions explicitly.

### DOC-B09 — Architecture and evidence claims overreach

- README says “six” exit criteria while the plan defines eight.
- Evidence does not contain raw offline-suite or Cloudflare state/token-scope proof.
- The split-horizon evidence records a public IP despite the runbook redaction rule.
- The laptop evidence checks Windows while the documented endpoint is Debian WSL2.
- Architecture ownership tables omit Microsoft 365 records and Azure VM
  auto-registration.
- “Both answers under version control” is false for the manually created Spatium override.
- Phase 4 and repository guidance say Python 3.10+, while `pyproject.toml` requires 3.11+.

## Validation Evidence

| Check | Result |
|---|---|
| `uv run pytest -q` | **PASS — 305 tests** on the active Python 3.13 environment |
| Minimum runtime | **PASS — 305 tests** with isolated Python 3.11 |
| Blank credentials + dead outbound proxies | **PASS — 305 tests** |
| Build/install console entry point | **PASS** — sdist/wheel built; clean install; help=`0`, missing config=`1` |
| `uv lock --check` / `uv pip check` | **PASS** |
| `uv run ruff check .` | **FAIL — Ruff not installed by declared dev dependencies** |
| Ruff via `uvx` fallback | 18 non-blocking style/exception-selection findings; no new correctness finding |
| `terraform fmt -check -recursive` | **PASS** |
| `terraform validate` — Cloudflare root | **PASS** |
| `terraform validate` — lab root | **PASS** |
| `tflint --recursive` | **PASS** with current configuration |
| Checkov — Terraform | **PASS — 38 passed, 0 failed, 15 justified skips** |
| Checkov — tracked GitHub Actions | **PASS — 249 passed, 0 failed, 3 skips** |
| Actionlint | **PASS** |
| Snapshot integrity/allowlist | **PASS — 3 records, verified checksum, 0 unowned keys** |
| Combined Spatium Compose configuration | **PASS** |
| Local Markdown links | **PASS — 0 missing across authoritative docs/plans** |
| Tracked secret/prohibited-file scan | **PASS — no suspicious secret or prohibited state/key/tfvars file** |
| `git diff --check` | **PASS** |

A fresh Terraform plan was not run during this read-only review because the affected roots
use live remote state and credentials. Existing committed evidence was inspected, but it
does not substitute for a new reviewed plan after fixes.

## Repository Tooling Finding

The local knowledge graph is stale. `graphify-out/graph.json` was built at commit
`d5e9af1` on 2026-08-04, 65 commits behind reviewed HEAD `b898a39`. It contains 38
references to the deleted pre-src-layout provider paths, zero references to the current
`src/ddi_reconciler/providers/` paths, and cannot resolve `plan_edge`, `load_desired`, or
the current Azure provider. Run `graphify update .` after the fixes; do not use the current
graph as Phase 5 implementation evidence.

## Required Exit Conditions Before Phase 5

1. Fix CR-01 through CR-04 and add the exact regression cases described above.
2. Re-run the full suite, minimum-Python suite, Ruff, package smoke test, Terraform gates,
   and a second deep GSD code review with **zero Critical findings**.
3. Fix WR-01 before relying on nightly drift; make snapshot verification fail closed.
4. Correct the Phase 4 status, runbook, ADR-006, evidence scope, ownership tables, and
   Python-version claims.
5. Rebase the Phase 5 plan onto current workflow semantics. Complete Cloudflare backend
   discovery plus artifact upload/download/manifest/hash verification and preserve
   read-only/edit-token separation.
6. Either run the real tunnel-based split-horizon demonstration or formally redefine the
   criterion and schedule the missing architecture work.
7. Refresh the graph and verify it resolves the current provider/runner paths.

After these conditions pass, Phase 5 can receive a new go/no-go review. Until then, only
planning, documentation repair, and blocker remediation should proceed.

---

_Review workflow: requested `gsd-code-review`, adapted to the repository's Superpowers
Phase 4 plan because no `.planning/` GSD phase registry exists. No source or infrastructure
was modified and no commit was created._
