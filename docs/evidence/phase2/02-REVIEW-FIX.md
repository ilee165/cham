---
phase: 02-azure-core
fixed_at: 2026-08-03T16:10:42Z
review_path: docs/evidence/phase2/02-REVIEW.md
iteration: 1
findings_in_scope: 18
fixed: 16
skipped: 2
status: partial
---

# Phase 2: Code Review Fix Report (combined — Warning pass + Info pass)

**Fixed at:** 2026-08-03T16:10:42Z
**Source review:** docs/evidence/phase2/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 18 (0 critical, 6 warning, 12 info; fix_scope: all)
- Fixed: 16 (WR-01..WR-06; IN-02, IN-03, IN-04, IN-05, IN-07, IN-08,
  IN-09, IN-10, IN-11, IN-12)
- Skipped: 2 (IN-01 and IN-06 — each changes deployed-resource behavior the
  operator must own; details and ready-to-apply guidance below)
- Post-review safety corrections also supersede the pre-review recovery plan,
  replace automatic CI apply/destroy with exact saved-plan gates, and complete
  the flag-gated DNS Private Resolver link/NSG path.

Both passes ran in isolated git worktrees on temporary branches,
fast-forwarded onto `feat/plan-and-verify-phase-2` after verification. No
terraform plan/apply/destroy/state/import and no az mutations were run; state,
backends, tfvars, and `*.tfplan` files were never touched.

## Required state-backed plan review — the operator's checklist

No source-only review can promise an exact resource count. The documented
35-resource state contains the app VM and both NICs but no management VM, so a
safe plan must explicitly set app VM/NIC `true`, management NIC `true`, and
management VM `false` before planning. The deprecated shared `enable_test_vm`
flag cannot represent that state.

Against those state-aligned values, the code-relative NSG delta expected from
the original review fixes is:

1. **WR-01** — two added rules: `AllowOutboundForwardedToSpokes` (Outbound
   130) and `AllowWgTransferTransitFromSpokes` (Inbound 135).
2. **IN-10** — three changed destinations: `AllowWireGuardFromHome`,
   `AllowSSHFromHome`, and `AllowDNSFromRFC1918` go from `"*"` to the hub VM.

That is a review hint, not a plan assertion. Refresh the remote state, generate
a fresh saved plan from current `HEAD`, inspect every create/update/destroy,
confirm `enable_private_resolver = false`, and obtain a new SHA-256 approval.
Any pre-review Checkpoint C plan is superseded and must never be applied.

Other applied fixes are render-neutral under the documented defaults, with
two tfvars-dependent caveats:

- **WR-06 / custom_data:** render is byte-identical under default
  `wg_transfer_cidr`/`onprem_dns_ip`; if the gitignored tfvars overrides
  either, the plan will propose hub VM REPLACEMENT — stop and review.
- **IN-04 / IN-05 validations:** new plan-time validations must pass your
  tfvars values. They fail only if (a) a CIDR/IP value is malformed, (b)
  `onprem_dns_ip` lies outside BOTH `wg_transfer_cidr` and
  `onprem_address_space` (a placement the tunnel's AllowedIPs could never
  route anyway), or (c) `budget_start_date` is not `YYYY-MM-01T00:00:00Z`
  (or `+00:00`) form. Fix the value, not the validation.

## Fixed Issues

### WR-01: Hub NSG has no outbound rules — tunnel-initiated traffic toward spokes dropped at the hub NIC

**Files modified:** `terraform/modules/hub/main.tf`
**Commit:** 31f81fa
**Applied fix:** Added `AllowOutboundForwardedToSpokes` (priority 130,
Outbound, src `[var.onprem_address_space, var.wg_transfer_cidr]` -> dst
`var.spoke_address_spaces`) and `AllowWgTransferTransitFromSpokes` (priority
135, Inbound, src spokes -> dst `var.wg_transfer_cidr`), exactly as the review
prescribed, with comments explaining the decapsulated-flow rationale.
**Plan impact:** real NSG diff — see checklist item 1. Requires human
verification: confirm the two new rules (and nothing else unexpected) appear.

### WR-02: Spoke-to-spoke "allow via hub only" comment contradicts the implemented deny

**Files modified:** `terraform/modules/spoke/main.tf`
**Commit:** 7ae1c32
**Applied fix:** Reviewer's option (a): rewrote the NSG comment to state the
real posture — spoke-to-spoke is fully denied, including via the hub — and
documented exactly which two rules to add if hub transit is ever wanted.
**Plan impact:** render-neutral (comment-only).

### WR-03: dns-resolver forwarding rule targets an unreachable address

**Files modified:** `terraform/modules/dns-resolver/variables.tf`, `terraform/modules/dns-resolver/main.tf`, `terraform/envs/lab/main.tf`
**Commit:** 722fc1b
**Applied fix:** Replaced the module's `onprem_dns_ip` input with `hub_dns_ip`
(required), pointed `target_dns_servers.ip_address` at it, wired
`hub_dns_ip = module.hub.vm_private_ip` from the caller. The
UDR-on-delegated-subnet alternative was rejected as unverified.
**Plan impact:** render-neutral while `enable_private_resolver = false`
(all module resources are count = 0).

### WR-04: `onprem_address_space` not passed to the hub module

**Files modified:** `terraform/envs/lab/main.tf`, `terraform/modules/hub/variables.tf`
**Commit:** 5e71bea
**Applied fix:** Added `onprem_address_space = var.onprem_address_space` to
the `module "hub"` block and removed the module-side default (both halves of
the reviewer's fix).
**Plan impact:** render-neutral (lab default equals the removed module
default, `10.20.0.0/16`).

### WR-05: Spoke CIDRs duplicated between hub transit allow-list and spoke blocks

**Files modified:** `terraform/envs/lab/main.tf`
**Commit:** c1cce66
**Applied fix:** Added `local.spoke_cidrs` and consumed it in all three places
(`spoke_address_spaces = values(local.spoke_cidrs)`, per-spoke
`address_space`). `values()` sorts by key, matching the previous literal order.
**Plan impact:** render-neutral (identical rendered values).

### WR-06: cloud-init hardcodes WireGuard addressing, ignoring `wg_transfer_cidr`/`onprem_dns_ip`

**Files modified:** `terraform/modules/hub/main.tf`, `terraform/modules/hub/cloud-init.yml.tpl`
**Commit:** 07f3c52
**Applied fix:** Derived `wg_interface_cidr` via
`cidrhost(var.wg_transfer_cidr, 1)` in the templatefile call; the template now
renders `Address = ${wg_interface_cidr}` and
`AllowedIPs = ${onprem_dns_ip}/32, ${onprem_cidr}` instead of literals.
**Plan impact:** render-neutral under default tfvars (byte-identical render);
requires human verification — if tfvars overrides either variable, the next
plan proposes hub VM REPLACEMENT via `custom_data`. Check before approving.

### IN-02: Test VM subnet chosen by `values(...)[0]` — lexicographic accident

**Files modified:** `terraform/modules/spoke/variables.tf`, `terraform/modules/spoke/testvm.tf`
**Commit:** 4bfbd8b
**Applied fix:** Added `test_vm_subnet_key` (string, default null) and a local
`test_vm_subnet_key = var.test_vm_subnet_key != null ? var.test_vm_subnet_key : one(keys(var.subnets))`;
the NIC now uses `azurerm_subnet.subnets[local.test_vm_subnet_key].id`. With
today's single-subnet maps `one(keys(...))` returns the sole key
(console-verified); adding a second subnet without setting the variable now
fails at plan time instead of silently re-homing the NIC.
**Plan impact:** render-neutral — same subnet ID resolves (`workload` /
`tools`), expression change only.

### IN-03: Module `location` defaults ("eastus") contradict the lab region

**Files modified:** `terraform/modules/hub/variables.tf`, `terraform/modules/spoke/variables.tf`, `terraform/modules/dns-resolver/variables.tf`
**Commit:** 616a4dc
**Applied fix:** Removed all three `default = "eastus"` and made `location`
required with a description explaining why no default exists. `terraform
validate` on the root confirms every caller already passes `var.location`.
**Plan impact:** render-neutral (no value changes; dead defaults removed).

### IN-04: No validation on CIDR/IP variables rendered into named.conf/WG/NSGs

**Files modified:** `terraform/envs/lab/variables.tf`, `terraform/modules/hub/variables.tf`
**Commit:** 54939ac
**Applied fix:** Root: IPv4-CIDR validations on `onprem_address_space` and
`wg_transfer_cidr`; bare-IPv4 validation on `onprem_dns_ip` plus the
reviewer's cross-check — membership asserted against `wg_transfer_cidr` OR
`onprem_address_space` (widened from the review's wg-only suggestion because
the WG `AllowedIPs` render makes an on-prem-resident DNS server equally
legitimate). Hub module: format validations on `hub_vm_ip`,
`onprem_address_space`, `wg_transfer_cidr`, `onprem_dns_ip` (membership check
kept root-only to avoid duplicate failure noise). All conditions were
evaluated offline in `terraform console` against positive and negative
samples; defaults pass.
**Plan impact:** render-neutral for resources; validations execute at plan
time — see checklist caveat (b).

### IN-05: Budget amount/thresholds magic numbers; `budget_start_date` unvalidated

**Files modified:** `terraform/envs/lab/variables.tf`, `terraform/envs/lab/main.tf`
**Commit:** f84ba3c
**Applied fix:** Promoted `amount` to `var.budget_amount` (number, default 50)
with the $200-credit rationale in the description; added a plan-time
validation requiring `budget_start_date` to be UTC midnight on the first of a
month (`Z` or `+00:00` forms accepted, both console-verified). The reviewer's
optional `Forecasted` notification was NOT added — it changes the deployed
budget's notification behavior (new alert emails) and is the operator's call.
**Plan impact:** render-neutral (default 50 equals the old literal); see
checklist caveat (c) for the validation.

### IN-08: Cloudflare version floor understates the `content`-attribute requirement; no tfvars example

**Files modified:** `terraform/cloudflare/main.tf`, `terraform/cloudflare/terraform.tfvars.example` (new)
**Commit:** d9cce2f
**Applied fix:** Raised the floor to `version = "~> 4.52"` with a comment
explaining the real requirement; added `terraform.tfvars.example` following
the envs/lab convention (TEST-NET-3 placeholder, note that the credential is
env-sourced, never tfvars). Offline validate confirms the committed lockfile
(4.52.8) satisfies the new constraint.
**Plan impact:** render-neutral (provider-constraint metadata + example file;
no resource change, no re-init needed).

### IN-09: dns-resolver module resources untagged — no `tags` variable

**Files modified:** `terraform/modules/dns-resolver/variables.tf`, `terraform/modules/dns-resolver/main.tf`, `terraform/envs/lab/main.tf`
**Commit:** 88186ed
**Applied fix:** Added `variable "tags"` (map(string), default {}), applied
`tags = var.tags` to the four taggable resources (resolver, inbound endpoint,
outbound endpoint, forwarding ruleset — rules and subnets take no tags), and
wired `tags = local.tags` from the caller. Schema verified by offline
validate.
**Plan impact:** render-neutral today (`enable_private_resolver = false`, all
resources count = 0). When the resolver is enabled, its cost-bearing
resources are created tagged and become visible to tag-scoped cost queries.

### IN-10: Hub NSG rules use destination `*` and the NSG spans both hub subnets

**Files modified:** `terraform/modules/hub/main.tf`
**Commit:** 0b8b1e9
**Applied fix:** Scoped the destinations of `AllowWireGuardFromHome`,
`AllowSSHFromHome`, and `AllowDNSFromRFC1918` from `"*"` to `var.hub_vm_ip`,
with a comment explaining the snet-shared inheritance hazard and the
post-DNAT evaluation that keeps home->public-IP traffic matching. Dataplane-
neutral today: the hub VM is the only resident of the associated subnets and
the sole SSH/WG/DNS endpoint (resolver subnets carry no NSG association).
The "own NSG for snet-shared" half of the suggestion is future work for when
that subnet gains residents.
**Plan impact:** real NSG diff — see checklist item 2. Tightening only; no
live flow crosses a non-hub-VM destination under these rules today.

### IN-11: ICMP diagnostics to the hub VM are blocked

**Files modified:** `terraform/modules/hub/main.tf`
**Commit:** 8b04ba7
**Applied fix:** Reviewer's first option — documented the block as intentional
next to `DenyAllOtherInbound`: why port-scoped rules never match ICMP, why the
deny precedes `AllowVnetInBound`, that "DNS works but ping fails" is expected
during verification, and the exact rule to add if ping is ever wanted. The
allow-rule option was deliberately NOT taken (wider ingress = operator's
decision, per fix policy).
**Plan impact:** render-neutral (comment-only).

### IN-12: `resource_provider_registrations = "none"` with no documented RP list

**Files modified:** `terraform/envs/lab/providers.tf`, `terraform/bootstrap/main.tf`
**Commit:** a1ae413
**Applied fix:** Added a comment block above each provider block listing the
required namespaces per root plus the one-time `az provider register` loop.
Lists were derived from the actual resources, deviating from the review's
combined list: there is no `Microsoft.PrivateDns` RP namespace — private DNS
zones and the DNS Private Resolver live under `Microsoft.Network`; envs/lab
needs no `Microsoft.Storage` (managed disks are `Microsoft.Compute`; backend
blob access is data-plane). envs/lab: Network, Compute, Consumption,
Resources. bootstrap: Storage, Resources, Authorization.
**Plan impact:** render-neutral (comment-only).

## Skipped Issues

### IN-01: MASQUERADE exclusion covers only 10.0.0.0/8, not all RFC1918

**File:** `terraform/modules/hub/cloud-init.yml.tpl:62-64`
**Reason:** skipped — fix forces hub VM replacement, which the operator must
schedule. The edit itself is mechanical, but ANY byte change to the cloud-init
template changes rendered `custom_data`, which is ForceNew on
`azurerm_linux_virtual_machine.hub` — the next plan would propose destroying
and recreating the live (deallocated) hub NVA in a region already at 4/4 core
quota, mid-way through a partially-applied Checkpoint C. Unlike WR-06, this
change cannot be made byte-neutral. Behavior is also correct today: the
`-o "$outbound_interface"` constraint keeps tunnel traffic off the MASQUERADE
rule.
**Ready patch for the next intentional hub re-image:** in both the `iptables
-C` and `iptables -A` lines, extend
`! -d 10.0.0.0/8` to `! -d 10.0.0.0/8 ! -d 172.16.0.0/12 ! -d 192.168.0.0/16`.
**Original issue:** SNAT skip rests on interface coupling rather than address
exclusion; breaks quietly if the tunnel network moves or a second egress path
appears.

### IN-06: Hub VM has no boot diagnostics while extensions are disabled

**File:** `terraform/modules/hub/main.tf:157-192` (VM resource)
**Reason:** skipped per fix policy — enabling boot diagnostics is an explicit
operator-owned change to the deployed VM (new diagnostic surface/cost
posture). If accepted, the fix is a one-line in-place update: add
`boot_diagnostics {}` (managed storage, no storage account) to
`azurerm_linux_virtual_machine.hub`; consider the same for the test VMs in
`modules/spoke/testvm.tf`.
**Original issue:** `allow_extension_operations = false` plus no
`boot_diagnostics` leaves no serial console/screenshot path when cloud-init
fails on the single point of failure for all spoke DNS and egress.

### IN-07: One `enable_test_vm` flag drives both spokes — quota-blocked partial applies cannot converge

**Files modified:** `terraform/envs/lab/variables.tf`,
`terraform/envs/lab/main.tf`, `terraform/envs/lab/terraform.tfvars.example`
**Post-review fix:** added nullable per-spoke VM and NIC overrides and passed
their resolved values to the two spoke instances independently. The spoke
module can now retain a NIC even when its VM is disabled, which represents the
quota-blocked partial apply. The old shared flag remains only as a compatibility
fallback for existing gitignored tfvars. Every new state-backed plan must set
all four values explicitly; the documented partial state is represented by app
VM/NIC `true`, management NIC `true`, and management VM `false`.
**Plan safety:** this code change does not authorize a plan or apply. The first
fresh plan must prove the app VM and both existing NICs are retained, the
management VM is not retried, and no unrelated destroy or replacement is
present.

## Verification performed

### Post-review correction verification

The approved follow-up corrections are recorded in
`docs/evidence/phase2/02-POST-REVIEW-CORRECTIONS.md`. Fresh static validation
passes, and a state-backed verification plan using the four explicit
partial-state flags reports 0 create, 1 hub-NSG update, 0 delete, and 0
replacement with the resolver disabled. The artifact is verification-only and
not approved because it was generated before committing these corrections.

- **Tier 1:** every edit applied via exact-match Edit semantics; worktree
  confirmed clean (`git status --porcelain` empty) after each commit; final
  full-tree recheck clean.
- **Tier 2:** `terraform fmt -check` on every modified `.tf` file after each
  fix, plus a final `fmt -check -recursive` over `terraform/` — all clean.
  (One formatting miss in IN-08 — a comment splitting an attribute alignment
  group — was caught by `fmt -check`, restructured, and amended before the
  branch was fast-forwarded.)
- **Full-root validation:** offline `terraform validate` re-run against the
  affected root after EVERY fix — envs/lab for IN-02/03/04/05/09/10/11/12,
  cloudflare for IN-08, bootstrap for IN-12; all "Success!". Run with
  `TF_DATA_DIR` pointing read-only at each root's existing initialized
  `.terraform` — no init, no provider downloads, backend never contacted.
- **Expression-level tests:** all new validation conditions (CIDR/IP regexes,
  the onprem_dns_ip membership check, the budget date regex, `one(keys(...))`)
  were evaluated offline in `terraform console` from a throwaway config with
  positive AND negative samples; all behaved as intended, and all defaults
  pass.
- **Not verified mechanically:** validation conditions execute at plan time
  (validate parses but does not evaluate them) and the operator's gitignored
  `terraform.tfvars` was not read — see the checklist caveats. No terraform
  plan/apply was run, per the session's hard safety constraints.

## Commits (oldest first)

| Commit  | Finding | Subject |
|---------|---------|---------|
| 31f81fa | WR-01 | fix(02): WR-01 hub NSG outbound transit + wg-transfer inbound allows |
| 7ae1c32 | WR-02 | fix(02): WR-02 align spoke NSG comment with implemented isolation posture |
| 722fc1b | WR-03 | fix(02): WR-03 point resolver forwarding rule at reachable hub BIND9 |
| 5e71bea | WR-04 | fix(02): WR-04 wire onprem_address_space into hub module explicitly |
| c1cce66 | WR-05 | fix(02): WR-05 single-source spoke CIDRs via local.spoke_cidrs |
| 07f3c52 | WR-06 | fix(02): WR-06 derive WireGuard addressing from module variables |
| 4bfbd8b | IN-02 | fix(02): IN-02 select test VM subnet by explicit key instead of sort order |
| 616a4dc | IN-03 | fix(02): IN-03 make module location a required input, drop eastus defaults |
| 54939ac | IN-04 | fix(02): IN-04 validate CIDR/IP inputs that render into named.conf, WG, and NSGs |
| f84ba3c | IN-05 | fix(02): IN-05 promote budget amount to a variable, validate start date at plan time |
| d9cce2f | IN-08 | fix(02): IN-08 raise cloudflare floor to ~> 4.52, add tfvars example |
| 88186ed | IN-09 | fix(02): IN-09 add tags input to dns-resolver module, wire local.tags |
| 0b8b1e9 | IN-10 | fix(02): IN-10 scope home/DNS NSG rule destinations to the hub VM |
| 8b04ba7 | IN-11 | fix(02): IN-11 document intentional ICMP block at the hub deny rule |
| a1ae413 | IN-12 | fix(02): IN-12 document required resource providers beside both provider blocks |

---

_Fixed: 2026-08-03T16:10:42Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
