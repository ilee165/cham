---
phase: 02-azure-core
fixed_at: 2026-08-03T15:37:55Z
review_path: docs/evidence/phase2/02-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-08-03T15:37:55Z
**Source review:** docs/evidence/phase2/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (WR-01..WR-06; fix_scope critical_warning, 0 critical)
- Fixed: 6
- Skipped: 0

All fixes were applied in an isolated git worktree on a temporary branch and
fast-forwarded onto `feat/plan-and-verify-phase-2` after verification. No
terraform plan/apply/state/az commands were run; state, backends, and
`*.tfplan` files were not touched.

## Fixed Issues

### WR-01: Hub NSG has no outbound rules — tunnel-initiated traffic toward spokes dropped at the hub NIC

**Files modified:** `terraform/modules/hub/main.tf`
**Commit:** 31f81fa
**Applied fix:** Added `AllowOutboundForwardedToSpokes` (priority 130, Outbound,
src `[var.onprem_address_space, var.wg_transfer_cidr]` -> dst
`var.spoke_address_spaces`) and `AllowWgTransferTransitFromSpokes` (priority
135, Inbound, src spokes -> dst `var.wg_transfer_cidr`), exactly as the review
prescribed, with comments explaining the decapsulated-flow rationale.
**Verification note:** requires human verification — this is the one fix that
intentionally produces a real NSG diff on the next plan. Confirm the two new
rules (and nothing else) appear when the plan is reviewed.

### WR-02: Spoke-to-spoke "allow via hub only" comment contradicts the implemented deny

**Files modified:** `terraform/modules/spoke/main.tf`
**Commit:** 7ae1c32
**Applied fix:** Took the reviewer's option (a): rewrote the NSG comment to
state the real posture — spoke-to-spoke is fully denied, including via the hub
— and documented exactly which two rules (hub inbound spoke->spoke allow +
sibling-spoke allow below priority 200) to add if hub transit is ever wanted.
Comment-only change; zero plan diff. Actually implementing inter-spoke transit
is an infrastructure design decision deliberately left to the operator.

### WR-03: dns-resolver forwarding rule targets an unreachable address

**Files modified:** `terraform/modules/dns-resolver/variables.tf`, `terraform/modules/dns-resolver/main.tf`, `terraform/envs/lab/main.tf`
**Commit:** 722fc1b
**Applied fix:** Replaced the module's `onprem_dns_ip` input with `hub_dns_ip`
(described, required), pointed `target_dns_servers.ip_address` at it, and wired
`hub_dns_ip = module.hub.vm_private_ip` from the caller (reviewer's primary
recommendation; the UDR-on-delegated-subnet alternative was rejected as
unverified). The unused `onprem_dns_ip` variable was removed from the module to
prevent the same trap recurring. No plan diff while
`enable_private_resolver = false` (all module resources are count = 0).

### WR-04: `onprem_address_space` not passed to the hub module

**Files modified:** `terraform/envs/lab/main.tf`, `terraform/modules/hub/variables.tf`
**Commit:** 5e71bea
**Applied fix:** Added `onprem_address_space = var.onprem_address_space` to the
`module "hub"` block and removed the module-side default (both halves of the
reviewer's fix), so the hub/spoke on-prem views can no longer diverge silently.
Lab default equals the removed module default (`10.20.0.0/16`), so this is
plan-neutral today.

### WR-05: Spoke CIDRs duplicated between hub transit allow-list and spoke blocks

**Files modified:** `terraform/envs/lab/main.tf`
**Commit:** c1cce66
**Applied fix:** Added `local.spoke_cidrs = { app = "10.10.4.0/22", mgmt =
"10.10.8.0/22" }` and consumed it in all three places
(`spoke_address_spaces = values(local.spoke_cidrs)`,
`address_space = local.spoke_cidrs.app` / `.mgmt`). `values()` sorts by key
(app, mgmt), matching the previous literal list order, so the rendered values
are identical — plan-neutral.

### WR-06: cloud-init hardcodes WireGuard addressing, ignoring `wg_transfer_cidr`/`onprem_dns_ip`

**Files modified:** `terraform/modules/hub/main.tf`, `terraform/modules/hub/cloud-init.yml.tpl`
**Commit:** 07f3c52
**Applied fix:** Added `wg_interface_cidr = "${cidrhost(var.wg_transfer_cidr,
1)}/${split("/", var.wg_transfer_cidr)[1]}"` to the templatefile call; template
now renders `Address = ${wg_interface_cidr}` and
`AllowedIPs = ${onprem_dns_ip}/32, ${onprem_cidr}` instead of literals.
**Verification note:** requires human verification. Under the lab defaults
(`wg_transfer_cidr = 172.16.0.0/24`, `onprem_dns_ip = 172.16.0.2`) the render
is byte-identical to the old literals, so `custom_data` (which forces VM
replacement on change) should show NO diff. The operator's gitignored
`terraform.tfvars` was not read; if it overrides either variable, the next plan
will propose hub VM replacement — check the plan for `custom_data` before
approving.

## Verification performed

- **Tier 1:** every edited section re-verified via the Edit tool's exact-match
  semantics; worktree left with no uncommitted changes after each commit.
- **Tier 2:** `terraform fmt` + `terraform fmt -check` passed on every modified
  `.tf` file after each fix (parse-level + canonical-format check).
- **Full root:** `terraform validate` on `terraform/envs/lab` succeeded
  ("Success! The configuration is valid."), covering all cross-module wiring
  changes. Run offline in the isolated worktree with `init -backend=false
  -input=false` against providers copied from the existing local cache — no
  provider downloads, backend never initialized or contacted.
- **Not verified mechanically:** the `.yml.tpl` render (no checker available;
  `validate` does not evaluate variable-dependent `templatefile`) — render
  equivalence for WR-06 is by construction, see its verification note. No
  terraform plan/apply was run, per the session's hard safety constraints; the
  two "requires human verification" items above are exactly the ones the next
  saved-plan review must confirm.

## Commits (oldest first)

| Commit  | Finding | Subject |
|---------|---------|---------|
| 31f81fa | WR-01 | fix(02): WR-01 hub NSG outbound transit + wg-transfer inbound allows |
| 7ae1c32 | WR-02 | fix(02): WR-02 align spoke NSG comment with implemented isolation posture |
| 722fc1b | WR-03 | fix(02): WR-03 point resolver forwarding rule at reachable hub BIND9 |
| 5e71bea | WR-04 | fix(02): WR-04 wire onprem_address_space into hub module explicitly |
| c1cce66 | WR-05 | fix(02): WR-05 single-source spoke CIDRs via local.spoke_cidrs |
| 07f3c52 | WR-06 | fix(02): WR-06 derive WireGuard addressing from module variables |

Expected plan impact when the operator next plans with default-matching tfvars:
only the WR-01 NSG rule additions. Info findings (IN-01..IN-12) were out of
scope (`fix_scope: critical_warning`) and remain open.

---

_Fixed: 2026-08-03T15:37:55Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
