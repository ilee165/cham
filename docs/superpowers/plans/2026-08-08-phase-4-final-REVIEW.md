---
phase: 04-cloudflare-reconciler-v2
reviewed: 2026-08-08T23:12:06Z
depth: deep
files_reviewed: 32
files_reviewed_list:
  - .github/workflows/drift.yml
  - .github/workflows/reconciler-tests.yml
  - .gitignore
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
  - ddi-reconciler/tests/test_config.py
  - ddi-reconciler/tests/test_desired_file.py
  - ddi-reconciler/tests/test_provider_azure.py
  - ddi-reconciler/tests/test_provider_cloudflare.py
  - ddi-reconciler/tests/test_provider_spatium.py
  - ddi-reconciler/tests/test_reconcile.py
  - ddi-reconciler/tests/test_runner.py
  - spatium/docker-compose.agent-group.yml
  - terraform/cloudflare/backend.auto.tfbackend.example
  - terraform/cloudflare/main.tf
  - terraform/cloudflare/terraform.tfvars.example
  - terraform/cloudflare/variables.tf
  - terraform/modules/hub/cloud-init.yml.tpl
  - terraform/modules/hub/main.tf
findings:
  critical: 4
  warning: 3
  info: 0
  total: 7
status: issues_found
---

# Phase 4: Final Code Review Report

**Reviewed:** 2026-08-08T23:12:06Z  
**Depth:** deep  
**Files Reviewed:** 32  
**Status:** issues_found

## Summary

The final Phase 4 implementation still has four proven blockers. Two Spatium response-validation gaps can falsely certify an incomplete or malformed desired-state read and thereby authorize destructive DNS deletes. Azure's auto-registration guard is vulnerable to a list-to-write race that can overwrite an automatically registered record. Cloudflare proxy mode is discarded during reads and never repaired during updates, so a supported external mutation cannot converge.

These are not repetitions of the previously fixed empty-truth, exact-repeated-page, observed-auto-registration, split-TTL, or Cloudflare pagination findings. Each blocker below was reproduced against the current code through the normal planning/provider path, and each identifies the precise gap in the current tests.

Validation performed during review:

- `uv run pytest -q`: **305 passed**.
- `terraform fmt -check -recursive`: passed.
- `terraform -chdir=terraform/cloudflare validate -no-color`: passed.
- `terraform -chdir=terraform/envs/lab validate -no-color`: passed.
- `uv run ruff check .`: could not run because Ruff is absent from the declared development environment (WR-03).

Passing tests and Terraform validation do not exercise the four reproduced failure paths.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Cross-page overlap can falsely certify an incomplete Spatium read and authorize deletion

**Classification:** BLOCKER (Critical)  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:274-327`  
**Issue:** `_walk_collection` rejects only a page that is byte-for-byte equal to the immediately previous page (`page_items == previous_page`). It appends every raw item, including duplicates, and certifies completeness when the raw list length equals the declared `total`. A partially overlapping page can therefore fill the count while omitting a different record. Later canonicalization collapses the duplicate, but `read_verified` remains true. The runner consequently treats the absent managed record as a real deletion from authoritative truth.

**Minimal reproduction:** A source declares `total=4`. Page 1 returns records `A, B`; page 2 returns `B, C`; live managed state also contains `D`. The current adapter returns canonical desired names `A, B, C` with `read_verified=True`, and `plan_edge(..., truth_complete=True)` emits `DELETE D`. The missing `D` was never disproven; duplicate `B` merely hid the incomplete walk.

**Why tests miss it:** `ddi-reconciler/tests/test_provider_spatium.py:187-203` covers disjoint pages, `:206-215` covers a short raw count, and `:279-287` covers only an exactly repeated full page. No test uses a partial cross-page overlap whose duplicate count masks a missing record.

**Impact:** An unstable offset/page API view can turn a transient pagination overlap into a successful destructive reconciliation. Phase 5 must not automate snapshot export or apply until this is fixed, because a false-complete snapshot can preserve and replay the wrong deletion intent.

**Fix:** Keep the first declared total stable across every page and track record identity across the entire walk, preferably by immutable API ID and otherwise by a canonical payload fingerprint. Reject any duplicate/overlap before returning data, and compare the unique identity count—not raw response length—to the declared total. Add a regression test for `A,B / B,C / total=4` that proves the read is unverified and deletion is refused.

### CR-02: `null` and wrong-typed Spatium fields are silently skipped while the read remains deletion-authoritative

**Classification:** BLOCKER (Critical)  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:383-408`  
**Issue:** Required API fields are coerced with `str(...)` before validation. In particular, JSON `null` in `record_type` becomes the string `"NONE"`, is treated as an unsupported type, and is silently skipped. Lists and objects similarly become printable strings rather than malformed payloads. Completeness was already calculated from the raw collection count, so dropping the malformed managed record does not clear `read_verified`.

**Minimal reproduction:** Return a verified envelope with `total=2`: a valid `A` record plus `{name: "d", record_type: null, value: "10.0.0.4", ttl: 300}`. With live managed records `A` and `D`, the current provider returns only `A`, reports `read_verified=True`, and the planner authorizes `DELETE D`.

**Why tests miss it:** `ddi-reconciler/tests/test_provider_spatium.py:398-415` tests missing fields, the legacy `type` field, absent names/values, invalid TTLs, and non-object records. It does not test required keys that are present with `null`, list, object, or other wrong-typed values; the coercion masks those cases.

**Impact:** A schema regression or corrupt record in the authoritative API can delete the corresponding healthy edge record. This blocks Phase 5's unattended snapshot and healing flows for the same reason as CR-01: the truth gate is asserted for data the adapter discarded.

**Fix:** Validate that zone, name, record type, and value are strings (and nonempty where required) before normalization. Never use `str()` to make required payload fields valid. Only skip an unsupported record type after confirming it is a well-formed nonempty string. Add null/list/object cases and a runner-level regression proving no delete is authorized.

### CR-03: Azure auto-registration protection loses a list-to-write race and can overwrite a newly registered record

**Classification:** BLOCKER (Critical)  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/azure.py:75-123,190-200`  
**Issue:** The provider records auto-registration metadata only during `fetch_records`, then performs unconditional `create_or_update` and `delete` calls. No ETag or match condition is supplied even though the SDK operations support conditional writes. If an auto-registered record appears after the list snapshot but before an ADD, the cached guard says the name is absent and `create_or_update` replaces it. Post-apply verification then sees the requested manual value and reports success, concealing the clobber.

**Minimal reproduction:** The first Azure list is empty. Before the queued ADD executes, auto-registration creates `app -> 10.10.4.99`. The current provider calls `create_or_update(app, 10.10.4.30)` with no conditional keyword arguments, overwrites the auto-registered record, and reports the change. The final fetch contains `10.10.4.30`, so convergence succeeds.

**Why tests miss it:** The fake Azure service in `ddi-reconciler/tests/test_provider_azure.py:33-46` has static listing behavior and create/delete methods that neither accept nor assert conditional arguments. Tests at `:180-276` cover an auto-registered record already visible during fetch and the requirement to fetch before apply, but none inserts one between fetch and write.

**Impact:** This violates the project's explicit “never touch auto-registration” ownership boundary and can cause DNS data loss while exiting successfully. It blocks Phase 5 apply/healing automation.

**Fix:** Preserve record ETags from the fetch. Use a create-only precondition (`MatchConditions.IfMissing`/If-None-Match `*`) for ADD, and use the fetched ETag with `IfNotModified` for UPDATE and DELETE. Treat a precondition failure as a readable concurrency refusal: re-fetch, re-plan, and refuse any now-auto-registered key. Extend the fake service to accept and assert those preconditions and simulate the arrival race.

### CR-04: Cloudflare proxy mode is neither modeled nor repaired, making supported tamper non-convergent

**Classification:** BLOCKER (Critical)  
**File:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:69,321-377,393-436`  
**Issue:** Create requests set `proxied: false`, establishing DNS-only as provider policy, but reads discard the `proxied` field and update requests never send it. A user can turn a managed, proxiable record orange-cloud. Cloudflare then forces its TTL to Auto (`1` in the API). The reconciler sees only TTL drift and PATCHes the TTL, which cannot repair proxy mode. Cloudflare documents that proxied records use an uneditable Auto TTL; the API documents `proxied` as record state and `ttl=1` as automatic ([TTL behavior](https://developers.cloudflare.com/dns/manage-dns-records/reference/ttl/), [DNS Records API](https://developers.cloudflare.com/api/resources/dns/subresources/records/)).

**Minimal reproduction:** Fetch an existing managed CNAME with the desired content, `proxied=true`, and `ttl=1`, while desired state is DNS-only with TTL 300. The current provider emits `PATCH {"ttl": 300}` and never requests `proxied=false`. With the record still proxied/Auto on the next fetch, post-apply verification raises `ConvergenceError`; the tamper cannot be healed. If desired TTL is also Auto, proxy-mode drift can instead be invisible because the field is never compared.

**Why tests miss it:** Cloudflare response fixtures in `ddi-reconciler/tests/test_provider_cloudflare.py` omit `proxied`. The TTL-only update test at `:129-148` explicitly expects a body containing only `{"ttl": 600}`. There is no proxy-mode tamper or post-apply convergence test.

**Impact:** The current managed `demo` CNAME can have externally visible DNS semantics changed in a way reconciliation cannot heal. Phase 5's tamper-and-heal acceptance flow and unattended drift handling are not reliable until proxy state is enforced.

**Fix:** Require and read the API's `proxied` field for proxiable record types. Track DNS-only policy as provider-specific observed state, force an UPDATE when it is true, and PATCH `proxied:false` together with desired content/TTL. Re-fetch must prove it became false. Add an end-to-end provider/runner test for the exact proxied CNAME scenario.

## Warnings

### WR-01: Drift workflow silently accepts every unexpected process exit code

**Classification:** WARNING  
**File:** `.github/workflows/drift.yml:50-65`  
**Issue:** The step disables `errexit`, captures the pipeline's first status, and fails only when the value is exactly `1`. It then assumes every remaining result is `0` or `2`. Shell/tool failures such as `126`, `127`, `137`, or a future CLI contract regression therefore leave the reconciliation step green; because the issue step runs only for exactly `2`, they can also produce no alert.

**Phase 5 impact:** This does not corrupt DNS by itself, but it undermines the reliability of the scheduled monitoring gate Phase 5 intends to operationalize.

**Fix:** Enumerate the accepted contract and fail closed:

```bash
case "$exit_code" in
  0) ;;
  2) ;;
  *)
    echo "::error::cham-reconcile failed with unexpected exit code $exit_code"
    exit 1
    ;;
esac
```

Add a workflow-level shell test or extracted helper test for `0`, `1`, `2`, and an unexpected status.

### WR-02: Configurable spoke CIDRs are ignored by DNS access and NAT rules

**Classification:** WARNING  
**File:** `terraform/modules/hub/main.tf:92,113`; `terraform/modules/hub/cloud-init.yml.tpl:36-37,63-64`  
**Issue:** The module accepts `var.spoke_address_spaces` and uses it for transit NSG rules, but DNS/HTTP source rules, BIND ACLs, and NAT source matching are hardcoded to `10.10.0.0/16`. A valid caller that supplies spokes outside that aggregate gets internally inconsistent infrastructure: transit rules follow the variable while DNS access and Internet NAT silently do not.

**Phase 5 impact:** Current lab defaults remain inside `10.10.0.0/16`, so this does not block the present Phase 5 rollout. It is a correctness trap in the reusable module.

**Fix:** Pass the configured spoke CIDRs into the template and derive NSG source prefixes, BIND ACL entries, and one NAT rule per configured CIDR from the same input. Add a Terraform test/plan fixture with a non-`10.10.0.0/16` spoke and assert every generated rule follows it.

### WR-03: The documented development environment cannot run the configured linter

**Classification:** WARNING  
**File:** `ddi-reconciler/pyproject.toml:22-25`  
**Issue:** The repository configures Ruff and project instructions prescribe `uv sync --dev` followed by `uv run ruff check .`, but the development dependency group contains only pytest and responses. In the declared environment, `uv run ruff check .` fails with “program not found” instead of linting.

**Phase 5 impact:** This is not a Phase 5 functional blocker, but it makes a stated local quality gate non-reproducible and invites CI/local drift.

**Fix:** Add a pinned-compatible Ruff dependency to the development group, regenerate `uv.lock`, and run the documented check in `reconciler-tests.yml` so the gate cannot silently disappear.

## Phase 5 Gate

| Item | Phase 5 disposition |
|---|---|
| CR-01 | **Blocks** snapshot export and unattended reconciliation; incomplete truth can be certified. |
| CR-02 | **Blocks** snapshot export and unattended reconciliation; malformed truth can authorize deletes. |
| CR-03 | **Blocks** apply/healing; Azure auto-registration can be overwritten in a race. |
| CR-04 | **Blocks** Cloudflare tamper-heal acceptance; proxy-mode drift cannot converge. |
| WR-01 | Must be fixed before relying on scheduled drift monitoring as a trustworthy gate. |
| WR-02 | Non-blocking for current CIDRs; fix before treating the hub module as generally configurable. |
| WR-03 | Non-blocking for runtime; restore the promised quality gate. |

### Known Phase 5 plan defect (not counted as a Phase 4 code finding)

The current Phase 4 workflow deliberately reads `secrets.CLOUDFLARE_API_TOKEN_RO` (`.github/workflows/drift.yml:35-39`). The Phase 5 plan provisions only `CLOUDFLARE_API_TOKEN` and its replacement drift examples use that edit-capable token (`docs/superpowers/plans/2026-07-31-phase-5-cicd.md:127,182,207,257`). It also still describes the already-rewritten workflow as calling a nonexistent CLI (`:142`). This is a stale Phase 5 rollout contract, not a defect in the reviewed Phase 4 reconciler core.

Before Phase 5 execution, update the plan to provision a zone-scoped read-only token under `CLOUDFLARE_API_TOKEN_RO` for scheduled drift checks, retain the edit token only behind the protected apply environment, and remove the stale rewrite premise. Otherwise the current workflow fails for a missing secret, or an executor may regress the least-privilege boundary by replacing it with the edit token.

---

_Reviewed: 2026-08-08T23:12:06Z_  
_Reviewer: Codex (gsd-code-reviewer)_  
_Depth: deep_
