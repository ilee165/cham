---
phase: repository-current-fallback
reviewed: "2026-08-13T16:09:52Z"
depth: standard
grade: "D"
files_reviewed: 55
files_reviewed_list:
  - .github/workflows/apply.yml
  - .github/workflows/destroy.yml
  - .github/workflows/drift.yml
  - .github/workflows/plan.yml
  - .github/workflows/reconciler-tests.yml
  - ddi-reconciler/config.toml
  - ddi-reconciler/desired-records.json
  - ddi-reconciler/pyproject.toml
  - ddi-reconciler/src/ddi_reconciler/__init__.py
  - ddi-reconciler/src/ddi_reconciler/cli.py
  - ddi-reconciler/src/ddi_reconciler/config.py
  - ddi-reconciler/src/ddi_reconciler/desired_file.py
  - ddi-reconciler/src/ddi_reconciler/model.py
  - ddi-reconciler/src/ddi_reconciler/providers/__init__.py
  - ddi-reconciler/src/ddi_reconciler/providers/azure.py
  - ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py
  - ddi-reconciler/src/ddi_reconciler/providers/spatium.py
  - ddi-reconciler/src/ddi_reconciler/reconcile.py
  - ddi-reconciler/src/ddi_reconciler/runner.py
  - ddi-reconciler/tests/test_cli.py
  - ddi-reconciler/tests/test_cli_edge_isolation.py
  - ddi-reconciler/tests/test_config.py
  - ddi-reconciler/tests/test_desired_file.py
  - ddi-reconciler/tests/test_drift_exit_contract.py
  - ddi-reconciler/tests/test_provider_azure.py
  - ddi-reconciler/tests/test_provider_cloudflare.py
  - ddi-reconciler/tests/test_provider_spatium.py
  - ddi-reconciler/tests/test_reconcile.py
  - ddi-reconciler/tests/test_runner.py
  - ddi-reconciler/tests/test_workflow_gates.py
  - ddi-reconciler/tests/test_workflow_plan_confidentiality.py
  - scripts/check-drift-exit.sh
  - scripts/phase3-vm-watchdog.ps1
  - spatium/docker-compose.agent-group.yml
  - terraform/bootstrap/main.tf
  - terraform/bootstrap/variables.tf
  - terraform/cloudflare/main.tf
  - terraform/cloudflare/variables.tf
  - terraform/envs/lab/main.tf
  - terraform/envs/lab/outputs.tf
  - terraform/envs/lab/providers.tf
  - terraform/envs/lab/variables.tf
  - terraform/modules/dns-resolver/main.tf
  - terraform/modules/dns-resolver/outputs.tf
  - terraform/modules/dns-resolver/variables.tf
  - terraform/modules/hub/main.tf
  - terraform/modules/hub/outputs.tf
  - terraform/modules/hub/variables.tf
  - terraform/modules/private-dns/main.tf
  - terraform/modules/private-dns/outputs.tf
  - terraform/modules/private-dns/variables.tf
  - terraform/modules/spoke/main.tf
  - terraform/modules/spoke/outputs.tf
  - terraform/modules/spoke/testvm.tf
  - terraform/modules/spoke/variables.tf
findings:
  critical: 8
  warning: 7
  info: 0
  total: 15
status: issues_found
---

# Current Repository: Code Review Report

**Reviewed:** 2026-08-13T16:09:52Z  
**Depth:** standard  
**Files Reviewed:** 55  
**Status:** issues_found  
**Grade:** D — not release-ready

## Summary

This is a full-current-repository fallback review. The repository has no `.planning` project, no phase was supplied, and the exact 55 paths in the review request were treated as the authoritative scope. All 55 were reviewed; no source file was modified.

The implementation has unusually strong validation and several thoughtful fail-closed controls, but eight release-blocking defects remain in deletion provenance, provider reconciliation, secret transport, destructive workflow targeting, watchdog behavior, and Terraform ordering. Seven additional defects reduce robustness or reproducibility. The grade is therefore **D** despite the passing automated checks.

Validation evidence supplied for this review:

- Pytest: 382 passed.
- Ruff: passed.
- `terraform fmt -check`: passed.
- `terraform validate`: passed for `bootstrap`, `cloudflare`, and `envs/lab`.
- TFLint: passed with `terraform/.tflint.hcl`.
- Checkov: 52 passed, 0 failed, 15 skipped.

## Narrative Findings (AI reviewer)

### Critical Issues

#### CR-01: Snapshot integrity does not bind the flag that authorizes deletion

**Classification:** BLOCKER  
**File:** `ddi-reconciler/src/ddi_reconciler/desired_file.py:74-82,149-159,187-193,255-256`  
**Related:** `ddi-reconciler/src/ddi_reconciler/runner.py:253-262`

**Issue:** `_checksum()` hashes only the records array. `_verify_envelope()` validates that hash, then independently accepts `truth_verified`, and `load_desired()` returns that flag as deletion authority. Changing a checksum-clean snapshot from `"truth_verified": false` to `true` leaves its checksum unchanged and causes `load_desired(...).verified` to become true. A local production-path reproduction confirmed both facts. The altered snapshot can therefore authorize deletion of managed records omitted by an unprovable or partial source read, defeating the control described at lines 166-170.

**Fix:** Version the snapshot format and hash a canonical object containing at least `version`, `truth_verified`, `count`, and `records` (or integrity-bind the provenance flag separately). Treat legacy v1 snapshots as unverified for deletion until re-exported. Add a regression test that flips only `truth_verified` and requires load failure or `verified=False`.

#### CR-02: Fractional pagination totals are truncated and certify partial truth

**Classification:** BLOCKER  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:101-117,334-362`  
**Related:** `ddi-reconciler/src/ddi_reconciler/runner.py:253-262`

**Issue:** `_first_int_field()` accepts floats and arbitrary numeric strings, then calls `int(value)`. Thus a malformed total such as `1.9` becomes `1`. With one returned record, `_get()` sees `len(items) == declared_total` and returns `verified=True`; a production-path mocked response reproduced that result. Passing this certified partial truth to the runner authorizes deletion of another managed record. Negative and lossy pagination values are likewise accepted.

**Fix:** Accept only exact, nonnegative integers or canonical integer strings for totals, page counts, page numbers, offsets, and limits. Reject booleans, fractional floats, non-integral strings, negative values, and contradictory metadata before setting `read_verified`. Add pagination-metadata tests, including `1.9`, `-1`, and exponential/decimal strings.

#### CR-03: A bearer token is sent over non-loopback plaintext HTTP

**Classification:** BLOCKER  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:145-167`

**Issue:** When a token is supplied, the provider installs `Authorization: Bearer ...`. For `http://` endpoints outside loopback it prints a warning but proceeds, transmitting the credential in cleartext on every request. Any on-path or LAN observer can recover and reuse the Spatium credential. The localhost default is safe; the defect is the accepted authenticated remote-HTTP configuration.

**Fix:** Raise `ConfigError` or `RuntimeError` whenever a token is set and the endpoint is non-loopback HTTP. If an insecure development escape hatch is indispensable, require an explicit non-persisted opt-in and make refusal the default. Replace the warning-only test at `tests/test_provider_spatium.py:578-594` with refusal coverage.

#### CR-04: Cloudflare cannot converge a record-type transition at one owner name

**Classification:** BLOCKER  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:451-477,491-510`  
**Related:** `ddi-reconciler/src/ddi_reconciler/model.py:135-139`; `ddi-reconciler/src/ddi_reconciler/reconcile.py:73-83`

**Issue:** Record identity includes type, so changing one owner from CNAME to A/AAAA (or the reverse) becomes an add plus a delete. `CloudflareProvider.apply()` executes every add before every delete, although Cloudflare rejects an A/AAAA alongside a CNAME at the same name. A mocked production-path reproduction showed the POST failing before any DELETE. If only the new type remains allowlisted, the old conflicting type is not deletable at all, so that transition also cannot converge.

**Fix:** Preflight conflicts by canonical `(zone, name)`, not only full record key. Either (a) refuse with an explicit manual-transition procedure, or (b) require both old and new keys to be authorized and perform a deliberate delete-then-create transition with a documented availability window. Add A-to-CNAME and CNAME-to-A tests for both ownership configurations.

#### CR-05: The VM watchdog can deallocate resources in the wrong subscription

**Classification:** BLOCKER  
**File:** `scripts/phase3-vm-watchdog.ps1:8-24,148-162,194-201,234-242`

**Issue:** The watchdog accepts no subscription identifier and passes no `--subscription` argument to its authentication probe, deallocation, or instance-view calls. Resource-group and VM names are not globally unique. If the Azure CLI default context changes, the script can deallocate identically named VMs in another subscription while the intended lab VMs remain running and billing.

**Fix:** Add a mandatory GUID-validated `SubscriptionId`, verify the expected tenant/subscription at arm time, and pass `--subscription $SubscriptionId` to every Azure CLI call. Include the subscription in audit output and add dry-run/argument-construction tests proving every read and mutation is pinned.

#### CR-06: The watchdog mistakes an accepted async request for completed deallocation

**Classification:** BLOCKER  
**File:** `scripts/phase3-vm-watchdog.ps1:181-219,221-283`

**Issue:** `az vm deallocate --no-wait` returns success when Azure accepts the long-running operation, not when the VM reaches `deallocated`. On exit 0 the script permanently removes that VM from `$pendingDeallocations`. The later loop only polls state and never reissues a failed or stalled operation. If the accepted operation later fails, the cost-bearing VM remains running until the verifier exhausts its budget and throws.

**Fix:** Either omit `--no-wait` and handle completion explicitly, or keep each VM in a combined request/verification state machine until instance view proves `VM deallocated`; reissue failed or stale requests within the bounded retry budget. Test accepted-then-failed and accepted-but-stalled operations.

#### CR-07: Private Resolver subnet creation races hub peering creation

**Classification:** BLOCKER  
**File:** `terraform/envs/lab/main.tf:62-110,129-150`  
**Related:** `terraform/modules/dns-resolver/main.tf:21-53`; `terraform/modules/spoke/main.tf:161-193`

**Issue:** With `enable_private_resolver=true`, the resolver module writes two new subnets into the hub VNet while both spoke modules create peerings involving that same VNet. Both branches depend on hub outputs, but there is no graph edge ordering resolver subnet writes after the peerings. The repository already accounts elsewhere for Azure rejecting peering while a VNet remains `Updating` from `PutSubnetOperation`; this branch reintroduces that same race. An apply can fail after partially creating hourly billed resolver resources.

**Fix:** Serialize the resolver module after all peerings, for example by adding `depends_on = [module.spoke_mgmt]` to `module "dns_resolver"` (the management spoke already follows the app spoke), or expose a dedicated completion output that represents all peerings and depend on it. Add a plan-graph/workflow test that preserves this ordering when the feature flag is enabled.

#### CR-08: “Current main” is checked long before destructive apply

**Classification:** BLOCKER  
**File:** `.github/workflows/apply.yml:115-128,219-226,306-319,403-414`  
**Related:** `.github/workflows/destroy.yml:285-297,385-392`

**Issue:** Each job checks that `source_commit` is current `main`, then performs artifact download, cloud login, and initialization before applying. Main can advance during that window, so a saved plan from a now-superseded commit still applies or destroys despite the workflow's explicit “main moved; generate a new plan” policy. The artifact hash remains intact; the broken invariant is freshness relative to main.

**Fix:** First define whether the immutable human-approved commit or continuously current main is authoritative. If current main is required, re-fetch and compare immediately adjacent to each `terraform apply`, use repository-wide concurrency to exclude overlapping plan/apply/destroy transitions, and test that a simulated branch advance aborts before mutation. If the approved commit is authoritative, remove the misleading freshness claim and explicitly document that policy.

### Warnings

#### WR-01: Malformed provider sections escape the CLI error contract

**Classification:** WARNING  
**File:** `ddi-reconciler/src/ddi_reconciler/config.py:47-59,109-112`  
**Related:** `ddi-reconciler/src/ddi_reconciler/cli.py:197-211,240-247`

**Issue:** The loader validates edge tables but blindly calls `.get()` on `[spatium]` and `[azure]`, and it accepts wrong-typed `base_url` and `resource_group` values. Valid TOML such as `spatium = "bad"` raises `AttributeError`; a numeric `base_url` fails later in `.rstrip()`. The CLI does not catch `AttributeError`, so users receive a traceback instead of the documented exit-1 operational error. A local reproduction confirmed this path.

**Fix:** Schema-validate `edges`, `spatium`, and `azure` as the expected collection/table types and validate both provider fields as nonempty strings. Convert every failure to `ConfigError`, and add CLI-level tests asserting exit 1 without traceback.

#### WR-02: A non-object Cloudflare response raises an uncaught exception

**Classification:** WARNING  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:128-137`  
**Related:** `ddi-reconciler/src/ddi_reconciler/cli.py:197-211,240-247`

**Issue:** `_request()` parses JSON and immediately calls `body.get`. A successful HTTP response containing valid JSON with a top-level list, string, number, or null raises `AttributeError`, bypassing the provider's `RuntimeError` and the CLI's handled operational-error path. A mocked `200 []` response reproduced the traceback-producing exception.

**Fix:** Require `isinstance(body, dict)` immediately after JSON parsing and raise a path-specific `RuntimeError` for any other top-level type. Add tests for list, scalar, and null bodies on both successful and error status codes.

#### WR-03: Cloudflare TTL validation can fail after earlier writes land

**Classification:** WARNING  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:280-285,406-413,451-510`  
**Related:** `ddi-reconciler/src/ddi_reconciler/model.py:112-113`

**Issue:** The canonical model accepts TTL 0, which Cloudflare rejects. `_check_ttl()` runs only inside each create/update operation, while `apply()` mutates the diff sequentially. A diff containing a valid first add and an invalid later add writes the first record, then deterministically fails on the second, leaving avoidable partial state.

**Fix:** Before resolving the zone or issuing any mutation, validate every desired add and update against Cloudflare's TTL range. Add a mixed valid/invalid diff test and assert that no POST, PATCH, or DELETE occurs.

#### WR-04: Privileged workflow executables are referenced by mutable versions

**Classification:** WARNING  
**File:** `.github/workflows/plan.yml:60-92,132-139,332-341`  
**Related:** `.github/workflows/apply.yml:110,138,174,179,301,329,362,367`; `.github/workflows/destroy.yml:62,79,84,280,307,341,346`; `.github/workflows/drift.yml:36-42,85,179`; `.github/workflows/reconciler-tests.yml:37-38`

**Issue:** Every third-party action uses a movable major tag, and the scheduled drift workflow installs unversioned latest `uv`. Retagging, upstream account compromise, or a bad major-tag update therefore changes executable code without repository review. Several affected jobs can mint Azure OIDC tokens or access environment/repository secrets.

**Fix:** Pin actions to reviewed full commit SHAs and pin/hash the `uv` version. Use Dependabot or equivalent update PRs so upgrades remain visible and reviewable.

#### WR-05: VM images use a mutable `latest` version

**Classification:** WARNING  
**File:** `terraform/modules/hub/main.tf:276-280`  
**Related:** `terraform/modules/spoke/testvm.tf:49-53`

**Issue:** Both VM resources specify `version = "latest"`. The saved plan therefore reviews a mutable marketplace reference rather than the exact image build that Azure may provision, weakening the repository's exact-plan/reproducibility guarantees and allowing an upstream image change to alter boot behavior without a code diff.

**Fix:** Pin a known-good image version and update it deliberately through reviewed dependency changes. If automatic patch uptake is intentional, document that exception and add post-provision health checks that fail and deallocate broken VMs.

#### WR-06: Individually valid CIDRs may overlap and break routing

**Classification:** WARNING  
**File:** `terraform/envs/lab/main.tf:12-21`  
**Related:** `terraform/envs/lab/variables.tf:59-78,103-123`

**Issue:** `onprem_address_space` and `wg_transfer_cidr` are validated only as RFC1918 ranges. Values such as `10.10.0.0/16` pass but overlap the fixed hub (`10.10.0.0/22`), spoke, or resolver networks; the two variables may also overlap each other. Those accepted configurations create ambiguous WireGuard AllowedIPs, UDRs, and interface routes and can disconnect hub/spoke/on-prem traffic.

**Fix:** Add root-level cross-variable checks/preconditions proving pairwise non-overlap among hub, both spokes, both resolver subnets, on-prem, and WireGuard transfer ranges. Include boundary-touching and containment cases in Terraform tests.

#### WR-07: Invalid WireGuard keys can create a broken billing VM

**Classification:** WARNING  
**File:** `terraform/envs/lab/variables.tf:126`  
**Related:** `terraform/modules/hub/variables.tf:217-220`; `terraform/modules/hub/main.tf:252-303`

**Issue:** `wg_peer_public_key` is an unconstrained string. An empty or malformed repository secret passes planning and is rendered into cloud-init; Azure can still create and bill the hub VM while WireGuard configuration fails and the advertised hybrid path is unusable.

**Fix:** Validate the WireGuard public-key wire shape (44-character Base64 encoding of 32 bytes) at both the root and reusable module boundary, reject empty/whitespace values, and add invalid-secret plan tests.

---

_Reviewed: 2026-08-13T16:09:52Z_  
_Reviewer: Codex (gsd-code-reviewer)_  
_Depth: standard_

---

## Resolution (2026-08-15)

All 15 findings are fixed. The work was governed by
`docs/superpowers/plans/2026-08-13-review-remediation.md` and landed as four
PRs through the normal gate, in the plan's merge order A → C → B → D. Every
fix carries a regression test that fails on the pre-fix code; where a live
reproduction is unreachable from CI (C1's provisioning race, B1's
branch-advance race, D2's stalled Azure operation) the test is a structure
pin that still fails on the pre-fix tree.

| Finding | Classification | Fixed in |
| --- | --- | --- |
| CR-01 — snapshot integrity does not bind the deletion-authorizing flag | BLOCKER | [PR #20](https://github.com/ilee165/cham/pull/20) |
| CR-02 — fractional pagination totals certify partial truth | BLOCKER | [PR #20](https://github.com/ilee165/cham/pull/20) |
| CR-03 — bearer token over non-loopback plaintext HTTP | BLOCKER | [PR #20](https://github.com/ilee165/cham/pull/20) |
| CR-04 — record-type transition at one owner cannot converge | BLOCKER | [PR #20](https://github.com/ilee165/cham/pull/20) |
| CR-05 — watchdog can deallocate in the wrong subscription | BLOCKER | [PR #28](https://github.com/ilee165/cham/pull/28) |
| CR-06 — accepted async request mistaken for completed deallocation | BLOCKER | [PR #28](https://github.com/ilee165/cham/pull/28) |
| CR-07 — resolver subnet creation races hub peering creation | BLOCKER | [PR #21](https://github.com/ilee165/cham/pull/21) |
| CR-08 — "current main" checked long before destructive apply | BLOCKER | [PR #22](https://github.com/ilee165/cham/pull/22) |
| WR-01 — malformed provider sections escape the CLI error contract | WARNING | [PR #20](https://github.com/ilee165/cham/pull/20) |
| WR-02 — non-object Cloudflare response raises uncaught | WARNING | [PR #20](https://github.com/ilee165/cham/pull/20) |
| WR-03 — Cloudflare TTL validation can fail after earlier writes land | WARNING | [PR #20](https://github.com/ilee165/cham/pull/20) |
| WR-04 — privileged workflow executables referenced by mutable versions | WARNING | [PR #22](https://github.com/ilee165/cham/pull/22) |
| WR-05 — VM images use a mutable `latest` version | WARNING | [PR #21](https://github.com/ilee165/cham/pull/21) |
| WR-06 — individually valid CIDRs may overlap and break routing | WARNING | [PR #21](https://github.com/ilee165/cham/pull/21) |
| WR-07 — invalid WireGuard keys can create a broken billing VM | WARNING | [PR #21](https://github.com/ilee165/cham/pull/21) |

**CR-06 reassessment (recorded here; the classification above is the
review's original).** The pre-fix verify loop already failed loudly on
budget exhaustion — detection was never missing, reissue was. The fix merges
request and verification into one per-VM state machine
(`pending-request → pending-verify → done`) that reissues a stalled
acceptance inside the same 30-minute budget, which keeps its terminal throw.

Each remediation PR was itself code-reviewed before merge in its own finding
namespace, and every Critical/Warning finding from those reviews was fixed
in-PR before merging — including PR #28's review catching that the frozen
2026-07-31 arming snippet, run verbatim against the new mandatory
`-SubscriptionId` contract, would wedge at an invisible prompt while the
arm-proof reported the watchdog armed (fixed by the canonical
`-NonInteractive` runbook snippet).

Live-proof carry-forwards, both tied to issue #18's next real session: the
apply-adjacent freshness check (CR-08) proves out on the next real
`apply.yml` dispatch, and the reissue state machine (CR-06) on the next
watchdog-armed VM window.
