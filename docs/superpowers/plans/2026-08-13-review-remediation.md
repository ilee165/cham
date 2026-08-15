# REVIEW.md Remediation Plan — 15 findings, 4 PRs

**Source:** `docs/REVIEW.md` (Codex, 2026-08-13, grade D — 8 critical, 7 warning).
**Validation:** every finding was re-verified against source before this plan was
written. 15/15 are factually accurate. CR-06 keeps its original review severity
in this plan and in the findings record; the reassessment — the verify loop
exists and fails loudly, the missing piece is reissue — is recorded in the
resolution table when Task E lands, not silently substituted here.

**Decisions taken with the operator (2026-08-13), binding on this plan:**

| Finding | Decision |
|---|---|
| CR-08 | Current `main` is authoritative — re-verify immediately before a dedicated apply-only step + concurrency exclusion |
| CR-04 | Refuse cross-type transitions with a clear error naming the manual procedure |
| CR-03 | Hard refusal, no escape hatch — token + non-loopback http refuses at construction |
| WR-05 | Pin exact image versions; bump deliberately via PR |

**Merge order and PR numbering agree: A → C → B → D is PR 1 → 2 → 3 → 4.**
Rationale: PR 1 first — deletion-provenance defects (CR-01/02) are the
highest-blast-radius class in this repo and every fix is locally provable.
PR 2 second — latent-destructive Terraform, all local verification. PR 3 third —
workflow hardening, needs network to resolve action SHAs. PR 4 last — the
watchdog is session tooling, not in any unattended path.

Every fix lands with a regression test that fails against the pre-fix code —
no exceptions; where a live proof is out of reach the test is a structure pin
that still fails on `main`. Each PR goes through the normal gate (no direct
pushes).

## Global constraints

- No fix may weaken an existing fail-closed property. When in doubt, fail closed
  harder than the reviewer asked.
- `desired-records.json` format changes must land code + re-exported snapshot in
  the SAME commit — nightly drift reads both from one checkout, so a split lands
  a red night.
- The local SpatiumDDI stack must be up for the snapshot re-export (it is, as of
  plan date) so the v2 snapshot exports `truth_verified: true`.
- Public repo: no secrets, no state-account name, in any diff or test fixture.

---

## Task A — PR 1: reconciler correctness (CR-01, CR-02, CR-03, CR-04, WR-01, WR-02, WR-03)

Branch: `fix/review-reconciler`. All Python, all locally verifiable.

- [x] **A1 (CR-01): bind `truth_verified` into the snapshot hash.**
  `desired_file.py`: bump `SNAPSHOT_VERSION` 1→2. `_checksum()` hashes the
  canonical object `{"version", "truth_verified", "count", "records"}` (checksum
  field excluded from its own input). `_verify_envelope()` validates
  `truth_verified` is a bool BEFORE recomputing (the value participates in the
  hash), then recomputes over the same object — flipping any bound field breaks
  the checksum. Legacy v1 snapshots stay hard-rejected by the existing version
  check ("re-export it"); "loaded but unverified" is a state CI rejects anyway.
  Regression tests: (1) flip only `truth_verified` in a checksum-clean v2 file →
  load fails; (2) v1 envelope → load fails naming re-export; (3) round-trip
  save→load preserves `verified=True/False`.
- [x] **A2 (CR-01): migrate the committed snapshot via a sibling path.**
  An in-place `--export` onto the v1 file fails: `_prior_count()` validates the
  existing file with `_verify_envelope`, which now rejects version 1.
  `--allow-snapshot-shrink` is NOT the migration path — it exists to authorize
  record loss, and using it as a version bypass trains exactly the habit the
  flag's design warns about. Instead: export to a sibling temporary path,
  assert on the result that `version == 2`, `truth_verified == true`, and the
  records array is value-identical to the committed v1 records, then replace
  the tracked file with the verified export. Same commit as the code.
- [x] **A3 (CR-02): strict, latching pagination-integer parsing.**
  `spatium.py`: a declared integer field is valid only as a non-bool `int >= 0`
  or a string matching the canonical ASCII form `^(0|[1-9][0-9]*)$` — not
  Python `\d` (Unicode digits), no leading zeros, no floats including integral
  ones. Parsing is tri-state: *value*, *absent*, or *malformed* — and malformed
  LATCHES: once any recognized total/page/limit/offset key on any page is
  present-but-malformed, no later alias in the same body and no later page may
  restore verification for that fetch. Malformed flows into the existing
  "cannot be proven complete → `read_verified=False`" path (fail-closed, not an
  exception). Tests: `{"total": 1.9, "count": 1}` with one item must NOT verify
  (the alias fall-through case); malformed page-one total followed by a valid
  page-two total must NOT verify; `1.9`, `-1`, `"1e3"`, `"1.9"`, `"01"`, `2.0`,
  `True` each leave the fetch unverified; the review's exact repro (total `1.9`,
  one record) must not certify.
- [x] **A4 (CR-03): refuse token-over-plaintext.** Replace `_warn_if_plaintext`
  with a constructor refusal when a token is set and `base_url` is non-loopback
  `http://`. Loopback and https unchanged. Replace the warning-assertion test
  (`test_provider_spatium.py:578-594`) with refusal coverage + a
  loopback-stays-working test. CLI-level test: the failure exits 1 with the
  message, no traceback.
- [x] **A5 (CR-04): cross-type transition preflight — in the runner, the shared
  seam.** Both providers reject CNAME-vs-anything coexistence at one owner, and
  the runner is where desired and actual sets both exist. The preflight covers:
  (a) desired CNAME plus desired non-CNAME at the same owner (truth-side
  conflict, no edge involvement needed); (b) every desired add whose
  `(zone, name)` carries a different rtype among ALL observed edge keys where
  either side is CNAME — "observed" meaning the actual records PLUS the Azure
  provider's `blocked_keys`/`unparseable_keys` (records excluded from `actual`
  are still physically present at the edge and still conflict). Refusal is
  operational (exit 1) in both dry-run and apply — an unconvergeable edge
  reported as mere drift would mislead the nightly. The error names the manual
  procedure explicitly: temporarily manage only the old type, reconcile its
  deletion, then manage only the new type and reconcile creation. Tests:
  CNAME→A and A→CNAME under (i) both keys allowlisted, (ii) only the new key
  allowlisted, (iii) the conflicting edge record hidden in
  `blocked_keys`/`unparseable_keys`, (iv) truth-side CNAME+A at one owner — all
  refuse before any provider mutation.
- [x] **A6 (WR-01): schema-validate provider sections.** `config.py`: `edges`
  must be a list; `[spatium]`/`[azure]`, when present, must be tables;
  `base_url`/`resource_group` non-empty strings. All failures → `ConfigError`.
  CLI tests: `spatium = "bad"` and `base_url = 8000` exit 1 with the message,
  no traceback.
- [x] **A7 (WR-02): Cloudflare response-shape guard.** `_request()`: after
  `resp.json()`, non-dict body → `RuntimeError` naming path and type. Tests:
  `200 []`, `200 "x"`, `200 null`, and a non-2xx list body.
- [x] **A8 (WR-03): whole-diff TTL preflight.** `CloudflareProvider.apply()`
  already walks every record for zone binding before mutating; add
  `_check_ttl` for every `to_add` and `to_update.desired` in that same loop.
  Test: mixed valid/invalid-TTL diff → zero HTTP mutations issued.
- [x] **A9: close out.** Full suite + ruff. Every new test confirmed to fail on
  pre-fix code (run once against `main` before merge). PR through the gate.

## Task C — PR 2: Terraform (CR-07, WR-05, WR-06, WR-07)

Branch: `fix/review-terraform`. Verification: fmt/validate/tflint/checkov + tftest.

- [x] **C1 (CR-07): serialize resolver after peerings — with a regression
  test.** `module "dns_resolver"` gains `depends_on = [module.spoke_app,
  module.spoke_mgmt]` with a comment tying it to the
  `ReferencedResourceNotProvisioned` class and PR #13. The TDD rule holds here
  too: a structure pin or `terraform graph` assertion that FAILS on `main` —
  either a test parsing `envs/lab/main.tf` for the `depends_on` on
  `module.dns_resolver` (workflow-gates style), or a graph-output assertion
  that the resolver module's nodes depend on the spoke modules. Live proof
  additionally lands with issue #18's resolver-enabled session.
- [x] **C2 (WR-05): pin image versions.** Query current marketplace version for
  the Ubuntu SKU (`az vm image show --urn ...:latest`), pin in
  `modules/hub/main.tf:280` and `modules/spoke/testvm.tf:53`, comment the bump
  procedure. No lab needed for the query.
- [x] **C3 (WR-06): CIDR relationship preconditions — disjointness AND
  containment, each where it belongs.** Two different invariants:
  (a) top-level routed networks — hub `/22`, both spoke `/22`s,
  `onprem_address_space`, `wg_transfer_cidr` — must be pairwise DISJOINT;
  (b) the resolver inbound/outbound subnets must be CONTAINED WITHIN the hub
  VNet range (they are hub subnets — disjointness from the hub would be
  wrong), mutually disjoint, and disjoint from the hub's VPN and shared
  subnets. Implement via root-level cross-variable validation (Terraform ≥1.9)
  or a `check` block with address arithmetic in locals. tftest cases:
  containment violation (`10.10.0.0/16` onprem), boundary-adjacent disjoint
  (must pass), overlap between the two variables, resolver subnet outside the
  hub range (must fail), resolver subnet colliding with the VPN subnet (must
  fail).
- [x] **C4 (WR-07): WireGuard key shape validation.** `^[A-Za-z0-9+/]{43}=$`
  (44-char base64 of 32 bytes) at BOTH `envs/lab/variables.tf:126` and
  `modules/hub/variables.tf:217`. Reject empty/whitespace. Update the tftest
  fixture key to a valid-shaped dummy. tftest: malformed key fails plan.
- [x] **C5: close out.** fmt/validate/tflint/checkov/tftest. PR through the gate.

## Task B — PR 3: workflow hardening (CR-08, WR-04)

Branch: `fix/review-workflows`. Verification: actionlint + `test_workflow_gates.py`.

- [x] **B1 (CR-08): freshness immediately before a dedicated apply-only step.**
  In `apply.yml` (both jobs) and `destroy.yml` (apply-destroy job): split
  `terraform init` from `terraform apply` into separate steps, and place the
  re-verify step — `git fetch origin main` + compare `inputs.source_commit`,
  abort with the existing "main moved" message — IMMEDIATELY before the
  apply-only step, after init and every other preparatory action. The early
  check stays (fast feedback); the adjacent check is the enforcement.
- [x] **B2 (CR-08): mutation concurrency exclusion.** One shared
  `concurrency: { group: terraform-mutations, cancel-in-progress: false }` on
  the mutation jobs of plan/apply/destroy (saved-plan jobs included — a plan
  mid-apply is the TOCTOU seam). NOT on the PR-triggered `static`/`tests` jobs,
  which must keep running in parallel on PRs.
- [x] **B3 (WR-04): SHA-pin every executable input.** All `uses:` entries
  across the five workflows → full 40-hex commit SHA with `# vX.Y.Z` comment;
  resolve SHAs from each tag via `gh api` at implementation time. For uv, an
  exact version string alone does not satisfy pin-by-hash: replace drift.yml's
  `pip install -q uv` with the SHA-pinned `astral-sh/setup-uv` action plus an
  explicit `version:` input (matching reconciler-tests.yml's action, now also
  SHA-pinned), or install from an artifact verified against a recorded hash.
  Pin the checkov container by digest. Add `.github/dependabot.yml`
  (`github-actions` ecosystem) so pins don't fossilize.
- [x] **B4: pin the properties in tests.** Extend `test_workflow_gates.py`:
  (1) every `uses:` matches `@[0-9a-f]{40}`; (2) the apply-only step is
  immediately preceded by the freshness re-verify step in every mutation job;
  (3) mutation jobs declare the shared concurrency group. Structure pins, same
  style as the existing gate tests — a live branch-advance race is not
  reachable from CI and is deliberately not attempted.
- [x] **B5: close out.** actionlint + full suite. PR through the gate. Note in
  the PR body that the next real dispatch (issue #18's session) is the live
  proof of B1.

## Task D — PR 4: watchdog (CR-05, CR-06)

Branch: `fix/review-watchdog`. Session tooling — not in any unattended path.

- [x] **D1 (CR-05): subscription pinning.** Mandatory `SubscriptionId` param,
  GUID-validated via `[ValidatePattern]`. Every az invocation (`get-access-token`
  probe, `vm deallocate`, `vm get-instance-view`) gains
  `--subscription $SubscriptionId`. Arm-time probe verifies the subscription is
  reachable. Subscription appears in every audit log line.
- [x] **D2 (CR-06): reissue-capable state machine.** Merge the request and
  verify loops into one per-VM state machine: `pending-request` →
  `pending-verify` → done. A VM in `pending-verify` whose instance view still
  shows a running state N cycles after acceptance (~3 min) drops back to
  `pending-request` and the deallocate is reissued — all inside the existing
  30-minute budget, which keeps its loud terminal throw. `-DryRun` behavior
  unchanged.
- [x] **D3: argument-construction test.** Extend `-DryRun` to also print the
  fully-formed az argument vectors it WOULD run. New
  `tests/test_watchdog_args.py` (reconciler test tree, where the workflow-gate
  tests already live): invoke `pwsh -File ... -DryRun`, assert every printed az
  command carries `--subscription` and the pinned resource group;
  `pytest.mark.skipif` when `pwsh` is absent, with the skip reason naming what
  is lost — ubuntu CI runners ship pwsh, so CI always runs it.
- [x] **D4: close out.** Dry-run + real arm-time smoke against a dead deadline
  (probe fails fast without a lab — expected; the point is argument shape).
  PR through the gate.

## Task E — resolution record

- [x] **E1:** Append a Resolution section to `docs/REVIEW.md` (repo convention,
  cf. the PR #7/#8 review): one row per finding — fixed-in-PR link. CR-06's row
  keeps the original BLOCKER classification and records the reassessment there:
  the pre-fix verify loop already failed loudly on budget exhaustion; the fix
  adds reissue. Update memory. This lands with or after PR 4, not before the
  fixes it claims.

## Exit criteria

1. All 15 findings fixed, each with a regression test that fails on pre-fix
   code — including C1's structure pin.
2. Full suite, ruff, actionlint, fmt/validate/tflint/checkov, tftest all green.
3. `desired-records.json` is v2 with `truth_verified: true` and value-identical
   records, migrated via the sibling-path procedure (no shrink-flag bypass);
   the nightly after PR 1 merges is green and silent.
4. No direct pushes to `main`; four PRs through the gate in A → C → B → D order.
5. `docs/REVIEW.md` carries the resolution table.
