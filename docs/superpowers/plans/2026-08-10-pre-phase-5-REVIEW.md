---
date: 2026-08-10
type: deep-code-review
scope: pre-phase-5 re-review of Phase 4 remediation (main@10503f7)
status: issues-found
grade: 89/100 (B+)
gate: PASS
files_reviewed: 52
findings:
  critical: 1
  warning: 3
  info: 5
  total: 9
---

# Pre-Phase-5 Deep Code Review — Second Review Required by the Phase 4 Quality Gate

**Reviewed:** 2026-08-10 · **HEAD:** `10503f7` (merge of PR #10) · **Prior review:** 2026-08-08, 62/100 (D-), gate FAIL
**Depth:** deep (cross-file: truth→model→diff→runner→providers, CLI exit codes end to end, CI trigger/permission/secret chains, Terraform module↔root variable flow and template rendering)

## 1. Executive summary

**Grade: 89/100 (B+). Gate: PASS — conditional. Phase 5: GO**, with one binding condition: **do not dispatch `plan.yml` or `destroy.yml` again until NEW-CR-01 is fixed**, and make that fix the first merged task of Phase 5.

All sixteen prior findings — CR-01..04, WR-01..03, DOC-B01..09 — are **verified fixed** in the current tree, each with the exact regression test or document change the prior review demanded, and none of the fixes introduced a regression I could find. The reconciler core now has **zero Critical findings**: the deletion-safety chain (fingerprint-deduplicated walk → stable declared total → typed field validation → `read_verified` → `truth_complete` gate) is coherent across all five modules it spans, Azure writes are conditional end to end, and Cloudflare proxy drift is observed, forced, healed, and re-verified. 346 tests pass offline on Python 3.11, ruff and `terraform fmt` are clean. The one new Critical is not in the reconciler: the raw `tfplan`/`destroy.tfplan` binaries uploaded as workflow artifacts on this **public** repository embed GitHub-secret variable values, the full state snapshot, and the backend storage-account name this repo otherwise carefully masks. The channel is dormant (it leaks only for 3 days after a manual dispatch, and the lab is destroyed), the fix is small, and it sits squarely inside Phase 5's CI/CD scope — hence conditional PASS rather than FAIL.

## 2. Prior-finding verification

| ID | Verdict | Evidence |
|---|---|---|
| CR-01 overlapping Spatium pages certify incomplete truth | **VERIFIED FIXED** | `spatium.py:288-323` — whole-walk `seen_items` fingerprint (`json.dumps(item, sort_keys=True)`), any repeat is fatal; `:325-334` first declared total pinned, mid-walk change fatal; `:343-348` short-read fatal. Exact `A,B / B,C / total=4` repro pinned at `test_provider_spatium.py:291-303`; same-page duplicate `:306-314`; moving total `:317-328`. Residual narrow bypass → NEW-WR-01. |
| CR-02 wrong-typed truth fields silently dropped | **VERIFIED FIXED** | `spatium.py:371-393` `_string_field` requires `str` (no `str()` coercion), nonempty where required; applied to zone name `:436`, `record_type` `:449` (only a well-formed string may be judged unsupported), name `:452`, value `:455`; bool/uncastable TTL fatal `:457-466`; a truth record the model rejects is fatal, never skipped `:476-482`. Null/list/object/empty parametrized cases `test_provider_spatium.py:441-469`; the exact null-`record_type` repro `:472-491`; SRV-still-skipped boundary `:493-503`. |
| CR-03 Azure list-to-write race clobbers auto-registration | **VERIFIED FIXED** | `azure.py:246-249` ADD is create-only (`MatchConditions.IfMissing`); `:250-258` UPDATE/DELETE carry the fetched ETag + `IfNotModified`; `:239-240` all ETags resolved before the first call (all-or-nothing); `:224-232` missing ETag refuses the whole diff; `:129-136` ETag captured/refreshed/popped per fetch; `:259-267` 412 duck-typed into a readable re-run refusal (no in-place retry — deliberate, per design). Fake client asserts the keyword-only preconditions (`test_provider_azure.py:50-69`); race repros `:312-330` (ADD), `:333-351` (DELETE); missing-ETag `:354-370`; refresh `:373-387`. Wire-shape body pinned against the real SDK model `:131-160`. |
| CR-04 Cloudflare proxy tamper cannot converge | **VERIFIED FIXED** | `cloudflare.py:365-374` `proxied` is a REQUIRED boolean on A/AAAA/CNAME reads (fatal if absent — no silent `false`); `:121,352-355` `proxied_keys` out of band, cleared per fetch; `runner.py:147-172,216-220` forces an UPDATE for a proxied managed key even when the diff says equal; `cloudflare.py:415-426` every PATCH to a proxiable type re-pins `proxied: false` (correctly NOT sent for TXT/PTR); `:484-489` a surviving record still proxied is PATCHed even at an equal TTL. Invisible-tamper (ttl=1 both sides) and visible-tamper repros heal in one apply and re-verify: `test_provider_cloudflare.py:618-667`; missing-field fatal `:670-679`; runner/CLI halves `test_runner.py:326-376`, `test_cli.py:550-561`. |
| WR-01 drift workflow accepts unexpected exit codes | **VERIFIED FIXED** | Gate extracted to `scripts/check-drift-exit.sh:12-23` — only `0|2` pass; `1` and `*` fail closed with `::error::`; `drift.yml:50-64` reads `PIPESTATUS[0]` and calls it. Contract tested as the artifact CI runs (`tests/test_drift_exit_contract.py`: 0, 2, 1, 3, 126, 127, 137, 255, missing arg). `reconciler-tests.yml:73-79` additionally fails closed on a `truth_verified=false` committed snapshot (the prior "prints but does not fail" gap). |
| WR-02 spoke CIDRs ignored by DNS/NAT paths | **VERIFIED FIXED** | `hub/main.tf:21-23` `internal_cidrs = [address_space] + spoke_address_spaces`; consumed by NSG DNS `:101` and HTTP `:122` sources, BIND `allow-query`/`allow-recursion` (`cloud-init.yml.tpl:36-37`), and the NAT RETURN/MASQUERADE loops (`:70-81`). NAT re-runs are idempotent (`-C` before `-I`/`-A`; RETURNs inserted at top always precede appended MASQUERADEs). Pinned by `tests/spoke_cidr_derivation.tftest.hcl:26-72` with a non-default `192.168.60.0/24` spoke and an assert that no `10.10.0.0/16` literal remains in cloud-init. Residual validation asymmetry → NEW-WR-02. |
| WR-03 ruff absent from declared dev environment | **VERIFIED FIXED** | `pyproject.toml:24-29` (`ruff>=0.12` in dev group); `reconciler-tests.yml:40-43` runs `uv run ruff check .` in CI; run during this review: "All checks passed!". TRY004 ignore is documented as the deliberate RuntimeError exit-1 contract (`pyproject.toml:31-37`). |
| DOC-B01 unperformed demo claimed complete | **VERIFIED FIXED** | `README.md:63-76` now: eight criteria, seven hold, the eighth "**redefined, not met**"; `split-horizon.txt:51-116` carries an explicit "NOT DEMONSTRATED" section with measurements. |
| DOC-B02 runbook instructs the non-working path | **VERIFIED FIXED** | `docs/runbook.md:183-197` states a tunnel client pointed at `10.10.0.10` does NOT see the internal page and that the browser-over-tunnel demo is scheduled in Phase 5 — "do not present it". |
| DOC-B03 ADR-006 vs operations mismatch | **VERIFIED FIXED** | `docs/decisions.md:61-83` amended (public-edge nightly, export procedure delegated to the runbook, CI rejects unverified snapshots); runbook has the referenced "Reconciler snapshot + drift operations (ADR-006)" section (`docs/runbook.md:149`). |
| DOC-B04 Phase 5 plan not rebased on live workflows | **VERIFIED FIXED** | `2026-07-31-phase-5-cicd.md:15-17,177` — plan now describes the live exact-artifact model as the baseline and withdraws the stale rewrite premise explicitly. |
| DOC-B05 Cloudflare CI incomplete in plan | **VERIFIED FIXED** (plan-level) | Same plan, Task 4(b): Cloudflare jobs must mirror "the same reviewed-artifact model and the partial-backend discovery". Implementation is Phase 5 work by design. |
| DOC-B06 plan regresses least privilege | **VERIFIED FIXED** | Plan `:24-25` pins `CLOUDFLARE_API_TOKEN_RO` (repo secret, Zone:Read+DNS:Read) for the schedule and the edit token only in the protected `lab` environment; `:160-162` names the "because it also works" regression as forbidden; drift snippets `:251,:313` use `_RO`. Live `drift.yml:39` matches. |
| DOC-B07 deferrals undisclosed/unscheduled | **VERIFIED FIXED** | README `:77-79` "Four things Phase 4 did not settle"; plan Task 7 (`:481+`) "every known deferral, named and scheduled" with a completion criterion (`:525`). |
| DOC-B08 stale plan snippets unsafe to follow | **VERIFIED FIXED** | Phase 4 plan header (`:5-16`): "⚠️ HISTORICAL PLAN — DO NOT EXECUTE ITS SNIPPETS", explains the unchecked A/B boxes and lists the known snippet/tree conflicts. |
| DOC-B09 evidence/claims overreach | **VERIFIED FIXED** | Public IP redacted per runbook rule (`split-horizon.txt:3`); Windows-vs-WSL2 correction recorded (`:77-81`); eight criteria in README; ownership tables now name M365 records and VM auto-registration (`docs/architecture.md:36,56-58,66`); Python 3.11 corrected in the plan tech stack; no remaining "3.10" claim in README/CLAUDE.md. |

Prior quality-gate exit conditions: 1–6 **met**. Condition 7 (graph refresh) **partially met** — see NEW-IN-05.

## 3. New findings

### NEW-CR-01: Saved-plan artifacts on a public repository leak secret values, the state snapshot, and the backend account name

**Severity:** Critical (secret disclosure channel)
**Files:** `.github/workflows/plan.yml:145-184` (plan + upload), `.github/workflows/destroy.yml:125-161` (destroy plan + upload)

The workflows upload the raw `tfplan` / `destroy.tfplan` binaries as workflow artifacts (3-day retention). A Terraform saved plan embeds: (a) **the value of every input variable**, including `TF_VAR_home_ip` — a GitHub **Secret** (`HOME_IP`), the /32 that is the sole permitted SSH/WireGuard source on the hub NSG — plus `subscription_id` and `alert_email`; (b) **the full prior state snapshot**, including the hub public IP the runbook's redaction rule protects and every NSG rule; (c) **the backend configuration**, including the state storage-account name that these very workflows `::add-mask::` out of their logs (`plan.yml:122`). On a public repository, any authenticated GitHub user can download workflow-run artifacts; `terraform show -json tfplan` then renders all of the above in cleartext. The "sanitized manifest" (`plan-summary.txt`, addresses + hash only) exists precisely because the team knows raw plan content is sensitive — but the unsanitized binary ships in the same artifact. GitHub secret masking applies to logs only, never to artifact files.

**Failure scenario:** operator dispatches `terraform-plan`; within the 3-day window anyone downloads `terraform-plan-<sha>`, learns the home IP (the one network the hub trusts, and the operator's approximate physical location), the hub public IP, the subscription ID, and the state account name.

**Suggested fix (pick one, before any further dispatch):**
1. Encrypt the plan before upload with a symmetric key held as a secret (e.g. `age`/`openssl enc`), decrypt in the apply job after environment approval — preserves the exact-artifact hash chain (hash the ciphertext).
2. Store the plan in the private state storage account (the apply job already authenticates to it via OIDC) and pass only the blob name + hash through the dispatch inputs.
3. Minimum stopgap: set `retention-days: 1` and document the exposure — not recommended as the end state.

### NEW-WR-01: A mid-walk bare-list body bypasses the CR-01 duplicate gate and can still certify an overlapping read

**Severity:** Warning (narrow residual of CR-01; requires the API to switch body shape between pages)
**File:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:298-302` vs `:314-323`, `:343-353`

In `_get`, a body that is a JSON list is `items.extend(body)` + `break` — its items are never passed through the `seen_items` fingerprint check, and `whole_body_was_a_bare_list` is only relevant on page 1. If page 1 is an envelope declaring a total and page 2 arrives as a bare list (a proxy that unwraps, an error page, a deployment that changes shape under load), duplicated items in that list count toward the total: `{items:[A,B], total:4, page:1}` then `[B,C]` yields `items=[A,B,B,C]`, `4 == total`, and `:353` returns `verified=True` because `declared_total is not None`. Canonicalization collapses the duplicate `B`, record `D` was never disproven, and a certified truth missing `D` is a delete order downstream — exactly the CR-01 failure mode through the one unguarded shape transition. No test covers a shape change mid-walk.

**Fix:** treat a list body on page > 1 as fatal ("pagination switched body shape mid-walk"), or route its items through the same fingerprint set. Add the envelope-then-bare-list regression test.

### NEW-WR-02: `address_space` and `spoke_address_spaces` reach the public-facing BIND ACL, NSG allows, and NAT script with no validation

**Severity:** Warning (gated — the lab root pins safe literals; same "reusable-module trap" class as the original WR-02)
**Files:** `terraform/modules/hub/variables.tf:35-38` (address_space — no validation), `:106-109` (spoke_address_spaces — no validation); sinks: `main.tf:21-23,101,122`, `cloud-init.yml.tpl:36-37,70-81`

`onprem_address_space` and `wg_transfer_cidr` carry elaborate RFC1918/width validations whose error messages explicitly reason "it renders into public-facing DNS ACLs and NSG allow rules" (`variables.tf:102,130`). The WR-02 fix routes `address_space` and every `spoke_address_spaces` entry into **the same sinks** via `local.internal_cidrs` — with zero validation. A caller passing `0.0.0.0/0` (or any public CIDR) as a spoke space silently turns the hub into an NSG-allowed, BIND-allowed open recursive resolver on a public IP; a malformed string becomes a boot-time `named.conf`/iptables failure instead of a plan error. The tftest proves propagation, not safety.

**Fix:** apply the identical RFC1918 + width validation to both variables (per-element for the list). Extend the tftest with an expected-failure `run` for a public CIDR.

### NEW-WR-03: An empty Azure record set at a managed key wedges convergence behind a misleading "re-run" instruction

**Severity:** Warning (fail-closed — no wrong mutation — but unconvergeable, with a remediation message that cannot work)
**File:** `ddi-reconciler/src/ddi_reconciler/providers/azure.py:143-144` vs `:246-249`, `:259-267`

`fetch_actual` skips a record set that exists with zero values (`if not values: continue`) **without recording it** in `unparseable_keys`/`blocked_keys`. If that name is a managed key: it is invisible to the diff → planned as ADD → `create_or_update` with `IfMissing` → **412**, because the (empty) record set exists. The 412 handler tells the operator "Re-run the reconciler: the fresh read will re-plan" — but every re-run repeats the identical skip→ADD→412 loop forever until a human deletes the empty set out of band. An empty record set is creatable via the API or a partially failed delete.

**Fix:** record empty-values sets in `unparseable_keys` with a "record set exists but carries no values" reason, so `runner.plan_edge` raises `UnwritableKeyError` naming the real cause before any write. Add a fake-client regression.

### NEW-IN-01: Truth-side split TTLs resolve first-row-wins, order-dependently

**File:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:467-469`
`grouped.setdefault(key, {"values": [], "ttl": ttl})` keeps the first row's TTL for a multi-row RRset; a later row's disagreeing TTL is silently ignored, so the desired TTL depends on API row order. Edge-side splits earned a whole out-of-band channel (`split_ttl_keys`); truth-side disagreement deserves at least a warning or a fatal, since "desired state" should not be order-dependent. **Fix:** raise (or warn) when a subsequent row's TTL differs from the entry's.

### NEW-IN-02: Float TTLs from truth are silently truncated

**File:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:461-466`
`int(raw_ttl)` accepts `300.9` and stores `300`, though the error message claims non-integer TTLs are rejected (only bools and uncastables are). **Fix:** reject non-integral values (`float(raw_ttl).is_integer()` check or `isinstance(raw_ttl, int)`).

### NEW-IN-03: `terraform apply` prints `hub_public_ip` into the public Actions log

**Files:** `.github/workflows/apply.yml:155-162`, `terraform/envs/lab/outputs.tf:1-4`
The apply step's final output block includes `hub_public_ip`, which the runbook's redaction rule keeps out of committed evidence; Actions secret-masking does not cover it (it is computed, not a secret). Log retention makes this a durable public record of the WireGuard endpoint. Subsumed operationally by the NEW-CR-01 fix if the plan moves to private storage; otherwise mark the output `sensitive = true` or drop it from CI output.

### NEW-IN-04: Spoke `DenyOtherSpokes` still hardcodes `10.10.0.0/16`

**File:** `terraform/modules/spoke/main.tf:84-93`
The hub module became CIDR-configurable (WR-02) but the spoke's east-west deny still names the default supernet; a spoke outside `10.10.0.0/16` would not be covered by it. Defense-in-depth only — peering topology already prevents spoke-to-spoke transit — but the module pair is now inconsistent about configurability.

### NEW-IN-05: Knowledge graph predates the remediation commits

**File:** `graphify-out/graph.json` (`built_at_commit: b898a39`)
Exit condition 7 asked for a refresh "after the fixes". The graph was refreshed on 2026-08-08 and now resolves `src/ddi_reconciler/providers/*` and `plan_edge` (the prior staleness is gone), but it was built at `b898a39` — before all nine PR #10 remediation commits — so it indexes the pre-fix provider code. Run `graphify update .` at `10503f7` before using it as Phase 5 implementation evidence.

## 4. What is good

- **The deletion-safety chain is genuinely coherent across five modules.** One rule — "absence from truth is only a delete order when the read is provably whole" — is enforced at the walk (`spatium.py:343-353`), the snapshot (`desired_file.py:125-159`), the runner (`runner.py:225-247`), the CLI flags, and CI (`reconciler-tests.yml:73-79` rejects an unverified committed snapshot). Every layer names its escape hatch and no layer defaults open.
- **The fixes were made at the right layer, with the exact adversarial repros pinned.** CR-01's fix is identity-across-the-walk, not a band-aid on the page comparison; CR-04's fix models proxy state out of band precisely because any in-band TTL value is legal desired data (`cloudflare.py:106-121`) — and the worst case (ttl=1 both sides) has an end-to-end test (`test_provider_cloudflare.py:653-667`).
- **Azure conditional writes are all-or-nothing by construction**: `_guard` + `_require_etag` both run before the first API call (`azure.py:234-240`), so a refused diff provably wrote nothing — matching the CLI's partial-apply accounting (`cli.py:223-243`), which itself distinguishes "failed before writing" from "may be half-mutated".
- **The apply trust chain is well defended**: regex-validated dispatch inputs, run-identity verification (event/branch/head_sha/conclusion/workflow path), artifact manifest binding (repo/commit/run/hash), current-main pinning, environment gating plus a reviewer-rule existence check (`apply.yml:47-127`). NEW-CR-01 is about artifact *confidentiality*, not this chain's *integrity*, which held up under scrutiny.
- **WR-02's fix ships with a real infrastructure test** — `spoke_cidr_derivation.tftest.hcl` asserts a non-default CIDR propagates into NSG rules, the BIND ACL, and both NAT rule families, and that no hardcoded supernet remains — credential-free via `mock_provider`.
- **Documentation now tells the truth at its own expense**: the split-horizon evidence documents what was NOT demonstrated with measurements (`split-horizon.txt:51-116`), the README says "redefined, not met", and the historical plan carries a do-not-execute banner. That is the hard half of documentation hygiene.
- **346 offline tests in ~5s, zero credentials, with CI pinning the offline property** by blanking every credential env var (`reconciler-tests.yml:49-55`).

## 5. Grade breakdown

| Dimension | Prior | Now | Justification |
|---|---:|---:|---|
| Functional design and integration | 17/20 | 19/20 | Out-of-band drift channels (split TTL, proxied) compose cleanly through runner and CLI; exit contract enforced at every boundary including argparse. |
| Correctness and data safety | 7/25 | 22/25 | All four Criticals fixed at the right layer with repros pinned; −3 for the narrow CR-01 shape-change bypass (NEW-WR-01), the Azure empty-set livelock (NEW-WR-03), and order-dependent truth TTLs (NEW-IN-01). |
| Tests and reproducibility | 16/20 | 19/20 | 346 offline tests incl. every prior finding's regression, a tftest, and the shell gate tested as the artifact CI runs; −1: console-script entry still exercised via `-m`, mid-walk shape change untested. |
| Infrastructure and security controls | 14/15 | 11/15 | OIDC, masking, input validation, and the exact-artifact integrity chain are strong; −3 NEW-CR-01 (public artifact secret exposure), −1 hub module validation asymmetry (NEW-WR-02). |
| Documentation, evidence, and handoff | 5/15 | 14/15 | All nine DOC-B findings fixed, honestly; deferrals named and scheduled; −1 residual minor claims drift risk (historical plan is banner-guarded, not corrected inline). |
| Maintainability and repository tooling | 3/5 | 4/5 | Ruff in dev group and CI; −1 graph refreshed pre-remediation (NEW-IN-05). |
| **Total** | **62/100 (D-)** | **89/100 (B+)** | |

## 6. Validation evidence

All run 2026-08-10 against `main@10503f7`, offline, no cloud credentials:

```
$ cd ddi-reconciler && uv run pytest -q
346 passed in 5.25s

$ uv run ruff check .
All checks passed!

$ uv run python --version
Python 3.11.15

$ terraform fmt -check -recursive        # repo root
(exit 0, no diffs)

$ git grep -nIE "(api[_-]?key|token|secret|password)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]" -- ':!*.md' ':!graphify-out'
(no matches)

$ git grep 'stchamtf[a-z0-9]{6}' / public-IP pattern scan over docs/
(no committed state-account name; no unredacted hub public IP — GitHub Pages
 anycast addresses in evidence are public constants)
```

`terraform validate`/`tflint`/`checkov` were not re-run (remote-state roots need credentials; the prior gate ran them at a tree whose Terraform diff since is the reviewed WR-02 change, which `terraform test` covers structurally). Graph check: `graphify-out/graph.json` `built_at_commit=b898a39`, resolves `src/ddi_reconciler/providers` (275 refs) and `plan_edge` (55 refs).

## 7. Required actions before Phase 5

Ordered. Item 1 is the gate condition; items 2–4 may land as early Phase 5 tasks; 5–6 are hygiene.

1. **NEW-CR-01 — stop the saved-plan artifact exposure** (encrypt the plan artifact, or move it to the private state storage account). Until merged: **do not dispatch `plan.yml` or `destroy.yml`.** Fold the same protection into the planned Cloudflare plan/apply pair before it is authored, so the leak pattern is not propagated.
2. **NEW-WR-01 — make a mid-walk body-shape change fatal in `spatium._get`** and add the envelope-then-bare-list regression test. This closes the last reachable edge of CR-01 before unattended snapshot export exists.
3. **NEW-WR-02 — add RFC1918/width validation to `address_space` and `spoke_address_spaces`** in the hub module, with an expected-failure tftest run.
4. **NEW-WR-03 — record empty-values Azure record sets in `unparseable_keys`** so a managed collision fails the plan with the true cause instead of a 412 livelock.
5. NEW-IN-01/02 — reject (or warn on) truth-side TTL disagreement and non-integral TTLs.
6. NEW-IN-03/04/05 — mark `hub_public_ip` output sensitive (or rely on the item-1 fix), align the spoke deny rule with the configurable CIDRs, and re-run `graphify update .` at `10503f7`.

---

_Reviewer: Claude (gsd-code-reviewer) · Depth: deep · 52 files fully read; README/runbook/decisions/plan documents and evidence spot-verified for the DOC-B fixes. No source files were modified; no commits were made._
