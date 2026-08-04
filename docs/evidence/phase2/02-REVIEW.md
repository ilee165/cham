---
phase: 02-azure-core
reviewed: 2026-08-03T14:52:43Z
depth: deep
files_reviewed: 17
files_reviewed_list:
  - terraform/bootstrap/main.tf
  - terraform/bootstrap/variables.tf
  - terraform/cloudflare/main.tf
  - terraform/envs/lab/main.tf
  - terraform/envs/lab/outputs.tf
  - terraform/envs/lab/providers.tf
  - terraform/envs/lab/terraform.tfvars.example
  - terraform/envs/lab/variables.tf
  - terraform/modules/dns-resolver/main.tf
  - terraform/modules/hub/cloud-init.yml.tpl
  - terraform/modules/hub/main.tf
  - terraform/modules/hub/variables.tf
  - terraform/modules/private-dns/main.tf
  - terraform/modules/spoke/main.tf
  - terraform/modules/spoke/outputs.tf
  - terraform/modules/spoke/testvm.tf
  - terraform/modules/spoke/variables.tf
findings:
  critical: 0
  warning: 6
  info: 12
  total: 18
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-08-03T14:52:43Z
**Depth:** deep
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Deep review of the Phase 2 Azure hub-spoke stack: 17 in-scope files plus companion files needed for cross-module tracing (`modules/hub/outputs.tf`, `modules/dns-resolver/{variables,outputs}.tf`, `modules/private-dns/{variables,outputs}.tf`, `terraform/cloudflare/variables.tf`, `.gitignore`, provider lockfiles).

**Verified sound (checked, not assumed):**

- **Secrets:** No `*.tfvars`, `*.tfstate`, `*.tfbackend`, `*.pem`, `*.key` files tracked by git (`git ls-files` empty; the on-disk `terraform/envs/lab/terraform.tfvars` is correctly ignored). `terraform.tfvars.example` uses TEST-NET-3 IP and placeholders. The cloud-init WireGuard config contains only a placeholder private key (`REPLACE_ON_HOST`) with the service explicitly disabled, so no secret lands in `custom_data`/state.
- **Backend/bootstrap consistency:** `rg-cham-tfstate` name matches between bootstrap and both backend blocks; `use_azuread_auth = true` is consistent with `shared_access_key_enabled = false` and `storage_use_azuread = true`. Lockfiles are committed for all three roots: azurerm 4.81.0 (supports `azurerm_storage_account_queue_properties`, `resource_provider_registrations`, `storage_account_id` on containers) and cloudflare 4.52.8 (supports the `content` attribute).
- **Module wiring:** Every module input referenced in `envs/lab/main.tf` exists with matching type; every consumed output (`vm_private_ip`, `vm_public_ip`, `vnet_id`, `vnet_name`, `vnet_address_space`, `testvm_private_ip`, `inbound_endpoint_ip`) exists. The `dns_resolver` output uses a lazy conditional so `enabled=false` cannot cause an index-out-of-range. No module cycles.
- **Template injection:** All five `templatefile` variables (`onprem_cidr`, `wg_transfer_cidr`, `lab_zone`, `onprem_dns_ip`, `wg_peer_public_key`) are supplied; the embedded awk/shell (`$(...)`, `$i`, `$NF`) is not Terraform template syntax, so no escaping bug.
- **Address plan:** Hub /22 subnets (10.10.0.0/27, 10.10.1.0/24) and flag-gated resolver /28s (10.10.2.0/28, 10.10.2.16/28) do not overlap; `hub_vm_ip` 10.10.0.10 is in snet-vpn's usable range; spoke subnets sit inside their /22s; seed A record 10.10.4.20 is inside the app workload subnet.
- **Spoke-initiated routing symmetry:** spoke→Internet transit works (UDR 0/0 → NVA, hub NSG rule 130, SNAT, stateful return); spoke→on-prem works (rule 140 inbound, WG-encapsulated egress, stateful return); spoke→hub DNS goes direct via the peering system route (more specific than 0/0 UDR), matched by rule 120. `allow_forwarded_traffic` is set on both peering directions. The `DenyOtherSpokes`(200)/`AllowIntraSpoke`(150) priority interplay works as the comment claims.
- **Kill-switch claim:** `.github/workflows/destroy.yml` referenced by the budget comment exists.

**Key concerns:** the NSG ruleset only models spoke-initiated flows — every hybrid flow initiated from on-prem/WireGuard toward the spokes dies at the hub NIC's default outbound deny (WR-01); the spoke-to-spoke "via hub" design stated in comments is denied by both NSGs (WR-02); the flag-gated Private Resolver forwards to a target it has no route to (WR-03); and three variable-vs-literal drift traps span envs/lab, the hub module, and the cloud-init template (WR-04..06). None block the Phase 2 checkpoint scope (spoke→Internet / spoke→on-prem transit), which is why there are no Criticals, but WR-01/WR-04/WR-06 will surface as Phase 3 breakage if not fixed first.

## Warnings

### WR-01: Hub NSG has no outbound rules — all on-prem/WireGuard-initiated traffic toward spokes is dropped at the hub NIC

**File:** `terraform/modules/hub/main.tf:49-126` (no outbound `security_rule` exists; inbound-only transit rules at 91-113), interacts with `terraform/modules/spoke/main.tf:54-76`
**Issue:** The transit rules (`AllowInternetTransitFromSpokes` 130, `AllowOnPremTransitFromSpokes` 140) cover only the inbound leg of spoke-initiated flows. For flows initiated from the tunnel side (laptop 172.16.0.2 or on-prem 10.20.0.0/16 → spoke), the packet materializes inside the hub VM (WG decapsulation) and exits the NIC as a *new outbound* flow with source 172.16.x/10.20.x. Neither source is in the hub subnets' `VirtualNetwork` service tag (no gateway, no route table on hub subnets), so default `AllowVnetOutBound` does not match; the destination is a peered VNet, so `AllowInternetOutBound` does not match; `DenyAllOutBound` (65500) drops it. The spoke NSG rules `AllowOnPrem` (110) and `AllowWireGuardTransfer` (111) exist precisely for these flows and are dead rules — the traffic can never arrive. Additionally, the return leg of spoke→172.16.0.0/24 flows relies on the destination matching the `Internet` tag in rule 130, which is undocumented behavior for RFC1918 space outside the VNet; there is no explicit inbound allow for spoke→wg-transfer destinations.
**Fix:** Add explicit outbound allows mirroring the transit intent, and an inbound rule for the wg-transfer destination:
```hcl
security_rule {
  name                       = "AllowOutboundForwardedToSpokes"
  priority                   = 130
  direction                  = "Outbound"
  access                     = "Allow"
  protocol                   = "*"
  source_port_range          = "*"
  destination_port_range     = "*"
  source_address_prefixes    = [var.onprem_address_space, var.wg_transfer_cidr]
  destination_address_prefixes = var.spoke_address_spaces
}

security_rule {
  name                       = "AllowWgTransferTransitFromSpokes"
  priority                   = 135
  direction                  = "Inbound"
  access                     = "Allow"
  protocol                   = "*"
  source_port_range          = "*"
  destination_port_range     = "*"
  source_address_prefixes    = var.spoke_address_spaces
  destination_address_prefix = var.wg_transfer_cidr
}
```
(Phase 2 verification passes without this because WireGuard is disabled; Phase 3 will fail with a symptom — one-way traffic — that is expensive to debug after the fact.)

### WR-02: Spoke-to-spoke "allow via hub only" is not implemented — forwarded inter-spoke traffic is denied by both the hub and destination-spoke NSGs

**File:** `terraform/modules/spoke/main.tf:1,35,79-88`; `terraform/modules/hub/main.tf:91-125`
**Issue:** The spoke module's comments state "deny spoke-to-spoke direct, allow via hub only" (lines 1, 35). Neither half of "via hub" works: (a) at the hub NIC, a forwarded app→mgmt packet (src 10.10.4.x, dst 10.10.8.x) matches no allow — rule 130 requires destination `Internet`, rule 140 requires destination on-prem — so `DenyAllOtherInbound` (4000) drops it before default `AllowVnetInBound` (65000); (b) even if the hub forwarded it, the NVA does not SNAT east-west traffic (`! -d 10.0.0.0/8` exclusion in the MASQUERADE rule), so the packet arrives at the destination spoke with the original 10.10.x source and hits `DenyOtherSpokes` (200), since `AllowFromHub` (100) matches only the hub /22. Either the comments misdescribe an intended full-isolation posture, or the intended transit path is missing rules in two NSGs. As written, the code and its stated design contradict each other.
**Fix:** Decide the intent and make code and comments agree. If isolation is intended, rewrite the comments ("spoke-to-spoke is fully denied, including via hub"). If hub transit is intended, add a hub inbound rule (src `var.spoke_address_spaces` → dst `var.spoke_address_spaces`, priority < 4000) and reorder the spoke NSG so forwarded spoke sources are permitted (e.g., an allow for the sibling-spoke CIDR ahead of `DenyOtherSpokes`).

### WR-03: dns-resolver forwarding rule targets an address unreachable from the resolver subnet — the flag-gated feature cannot work when enabled

**File:** `terraform/modules/dns-resolver/main.tf:90-101`; subnet at 38-53
**Issue:** The forwarding rule sends `${var.lab_zone}.` queries to `var.onprem_dns_ip` (172.16.0.2 — the laptop's WireGuard tunnel IP, reachable only through the hub VM's wg0 tunnel). The outbound endpoint egresses from `snet-resolver-out` (10.10.2.16/28), which has no route table; 172.16.0.2 matches no VNet/peering prefix, so the system default route sends it toward `Internet` next-hop where RFC1918 traffic is dropped. The query can never reach the laptop. The module's entire purpose (demonstrating on-prem conditional forwarding) fails on first enablement — during a paid, deliberately timeboxed session, which is the worst time to discover it.
**Fix:** Point the forwarding rule at the hub BIND9 VM, which is reachable in-VNet and already forwards the lab zone across the tunnel:
```hcl
target_dns_servers {
  ip_address = var.hub_dns_ip # 10.10.0.10, new variable wired from module.hub.vm_private_ip
  port       = 53
}
```
Alternatively attach a route table (172.16.0.0/24 → VirtualAppliance 10.10.0.10) to `snet-resolver-out` — but verify platform support for UDRs on dnsResolvers-delegated subnets before choosing that path.

### WR-04: `onprem_address_space` is not passed to the hub module — overriding it in tfvars silently splits hub and spoke views of on-prem

**File:** `terraform/envs/lab/main.tf:15-28`; `terraform/modules/hub/variables.tf:55-58`
**Issue:** The hub module block passes `wg_transfer_cidr` and `onprem_dns_ip` but omits `onprem_address_space`, so the hub silently falls back to its own default `10.20.0.0/16`. Both spoke blocks *do* receive `var.onprem_address_space` (lines 44, 64). The values coincide today only because the lab default equals the module default. If the operator ever sets `onprem_address_space` in `terraform.tfvars`, spoke UDRs and NSGs follow the new CIDR while the hub NSG rules 120/140 and the entire cloud-init render (WG `AllowedIPs`, BIND `allow-query`/`allow-recursion`) keep the stale default — on-prem DNS and transit break with no plan-time signal. The omission is inconsistent with the neighboring parameters, which marks it as an oversight rather than a choice.
**Fix:** In the `module "hub"` block add:
```hcl
onprem_address_space = var.onprem_address_space
```
and consider removing the default from `modules/hub/variables.tf` so the wiring is mandatory.

### WR-05: Spoke CIDRs are duplicated as literals between the hub's transit allow-list and the spoke module blocks

**File:** `terraform/envs/lab/main.tf:24,37,57`
**Issue:** `spoke_address_spaces = ["10.10.4.0/22", "10.10.8.0/22"]` (hub NSG transit sources) repeats the literals used as `address_space` in `spoke_app` (line 37) and `spoke_mgmt` (line 57). Editing a spoke CIDR without updating the hub list produces no error — spoke egress simply starts matching `DenyAllOtherInbound` (4000) at the hub, a silent full-egress outage for that spoke. Wiring `module.spoke_*.vnet_id`-style outputs back into the hub would create a module cycle (spokes already consume hub outputs), which is presumably why literals were used, but the single-source alternative was skipped.
**Fix:** Define once, consume in both places:
```hcl
locals {
  spoke_cidrs = { app = "10.10.4.0/22", mgmt = "10.10.8.0/22" }
}
# hub:    spoke_address_spaces = values(local.spoke_cidrs)
# spokes: address_space        = local.spoke_cidrs.app  # / .mgmt
```

### WR-06: cloud-init hardcodes WireGuard addressing (172.16.0.1/24, 172.16.0.2/32), ignoring the `wg_transfer_cidr`/`onprem_dns_ip` variables it renders elsewhere in the same file

**File:** `terraform/modules/hub/cloud-init.yml.tpl:22,28`
**Issue:** The template interpolates `${wg_transfer_cidr}` into the BIND ACLs (lines 35-36) and `${onprem_dns_ip}` into the forward zone (line 49), but the WireGuard `[Interface] Address = 172.16.0.1/24` and peer `AllowedIPs = 172.16.0.2/32, ...` are literals. `modules/hub/variables.tf:65-69` advertises `wg_transfer_cidr` as configurable; changing it (or `onprem_dns_ip`) re-renders NSG rules and BIND ACLs but leaves the tunnel itself on the old addressing — DNS ACLs and NSGs would then permit a network the tunnel no longer uses. This is an interface-contract violation inside one module: the variable is honored in three places and ignored in the two that matter most.
**Fix:** Derive the WG addressing from the variables in `main.tf`'s `templatefile` call and template:
```hcl
wg_interface_cidr = "${cidrhost(var.wg_transfer_cidr, 1)}/${split("/", var.wg_transfer_cidr)[1]}"
```
```
Address = ${wg_interface_cidr}
AllowedIPs = ${onprem_dns_ip}/32, ${onprem_cidr}
```

## Info

### IN-01: MASQUERADE exclusion covers only 10.0.0.0/8, not all RFC1918

**File:** `terraform/modules/hub/cloud-init.yml.tpl:62-64`
**Issue:** SNAT is skipped only for `-d 10.0.0.0/8`. Spoke traffic to 172.16.0.0/24 or 192.168.0.0/16 destinations would be masqueraded if it ever egresses the default interface. Today the `-o "$outbound_interface"` constraint saves the wg-transfer case (tunnel traffic leaves via wg0), so behavior is correct — but the correctness rests on interface coupling rather than the address exclusion, and breaks quietly if the tunnel network moves or a second egress path appears.
**Fix:** Exclude the RFC1918 aggregate: add `! -d 172.16.0.0/12` and `! -d 192.168.0.0/16` clauses (or a dedicated `RETURN` rule chain) alongside the existing 10/8 exclusion.

### IN-02: Test VM subnet chosen by `values(...)[0]` — lexicographic accident, not declaration

**File:** `terraform/modules/spoke/testvm.tf:10`
**Issue:** `values(azurerm_subnet.subnets)[0]` selects the subnet whose *key sorts first alphabetically*. With today's single-subnet maps it is deterministic, but adding a second subnet that sorts earlier (e.g., `bastion` before `workload`) silently re-homes the NIC, forcing NIC/VM replacement on the next apply.
**Fix:** Add a `test_vm_subnet_key` variable (default to the sole key) and index explicitly: `azurerm_subnet.subnets[var.test_vm_subnet_key].id`.

### IN-03: Module `location` defaults ("eastus") contradict the lab's region ("northcentralus")

**File:** `terraform/modules/hub/variables.tf:1-4`; `terraform/modules/spoke/variables.tf:6-9`; `terraform/modules/dns-resolver/variables.tf:7-10`
**Issue:** All three modules default `location` to `eastus` while every real instantiation passes `northcentralus`. Any future caller omitting `location` splits the deployment across regions (VNet peering still works, so it fails subtly — quota, latency, cost — not loudly).
**Fix:** Remove the defaults; make `location` a required input in all modules.

### IN-04: No validation on `onprem_address_space`, `wg_transfer_cidr`, `onprem_dns_ip`, `hub_vm_ip` — malformed values render straight into named.conf

**File:** `terraform/envs/lab/variables.tf:46-61`; `terraform/modules/hub/variables.tf:29-33,55-58,65-69,76-79`
**Issue:** `home_ip` gets a strict two-clause validation, but the values interpolated into BIND ACLs, WG config, NSG prefixes, and UDRs accept any string. A typo'd CIDR applies cleanly, then BIND fails to start at boot — a whole-lab DNS outage diagnosed on a VM with no boot diagnostics (IN-06). There is also no cross-check that `onprem_dns_ip` lies inside `wg_transfer_cidr`.
**Fix:** Add `can(cidrhost(var.x, 0))`-style validations to each CIDR/IP variable, and a validation on `onprem_dns_ip` asserting membership in `wg_transfer_cidr` via `cidrhost`/`cidrsubnet` containment.

### IN-05: Budget amount/thresholds are magic numbers and `budget_start_date` format is unvalidated

**File:** `terraform/envs/lab/main.tf:101-124`; `terraform/envs/lab/variables.tf:79-83`
**Issue:** `amount = 50` and thresholds 50/90 are hardcoded (the tfvars example narrative references a $200 credit — the relationship is undocumented). `budget_start_date` must be a first-of-month RFC3339 timestamp; anything else fails at apply time with an opaque Azure error despite being trivially checkable at plan time. Both notifications use the default `Actual` type — no forecasted early warning.
**Fix:** Promote `amount` to a variable with the rationale in its description; add `validation { condition = can(regex("^\\d{4}-\\d{2}-01T00:00:00Z$", var.budget_start_date)) ... }`; consider one `threshold_type = "Forecasted"` notification.

### IN-06: Hub VM has no boot diagnostics while extensions are also disabled — cloud-init failures are undebuggable

**File:** `terraform/modules/hub/main.tf:157-192`
**Issue:** `allow_extension_operations = false` (deliberate hardening) plus no `boot_diagnostics` block means a failed cloud-init (the exact failure mode IN-04 makes likely) leaves no serial console or screenshot path. The hub is the single point of failure for all spoke DNS and egress.
**Fix:** Add managed boot diagnostics (no storage account needed):
```hcl
boot_diagnostics {}
```

### IN-07: One `enable_test_vm` flag drives both spokes — quota-blocked partial applies cannot converge

**File:** `terraform/envs/lab/variables.tf:71-75`; `terraform/envs/lab/main.tf:46,66`
**Issue:** Live state already demonstrates the failure: the app test VM created, the mgmt VM is quota-blocked, and every apply with the shared flag on will retry (and fail on) the blocked VM. There is no way to express "app only."
**Fix:** Split into `enable_test_vm_app` / `enable_test_vm_mgmt` (or a `map(bool)`), passed per spoke instance.

### IN-08: Cloudflare version floor `~> 4.0` understates the real requirement of the `content` attribute; no tfvars.example for the cloudflare root

**File:** `terraform/cloudflare/main.tf:9-11,37,46`; `terraform/cloudflare/variables.tf:6-9`
**Issue:** `cloudflare_record.content` exists only in late 4.x releases; the constraint admits 4.0-4.3x where `terraform init` against a hand-edited or absent lockfile would fail. The committed lockfile (4.52.8) mitigates today. Separately, the root requires `www_public_ip` but ships no `terraform.tfvars.example`, unlike `envs/lab` which sets that convention.
**Fix:** Tighten to `version = "~> 4.52"` and add `terraform/cloudflare/terraform.tfvars.example` with a placeholder `www_public_ip`.

### IN-09: dns-resolver module resources are untagged — no `tags` variable exists

**File:** `terraform/modules/dns-resolver/main.tf` (all resources); `terraform/modules/dns-resolver/variables.tf`
**Issue:** Every other module accepts and applies `var.tags`; this module cannot. When the resolver is enabled, its cost-bearing resources (the ones the module warns cost ~$180/mo each) are the only untagged resources in the lab — invisible to tag-scoped cost queries.
**Fix:** Add `variable "tags" { type = map(string), default = {} }`, apply to the taggable resources, pass `tags = local.tags` from `envs/lab/main.tf`.

### IN-10: Hub NSG allows use destination `*` and the NSG spans both hub subnets — future snet-shared residents silently inherit SSH/WG/DNS exposure

**File:** `terraform/modules/hub/main.tf:55-89,128-136`
**Issue:** `AllowSSHFromHome`, `AllowWireGuardFromHome`, and `AllowDNSFromRFC1918` all use `destination_address_prefix = "*"`, and the same NSG is associated to `snet-vpn` and `snet-shared`. Any VM later placed in snet-shared is immediately SSH-reachable from home and DNS-reachable from all RFC1918 sources without any code change signaling it.
**Fix:** Scope destinations to the hub VM (`destination_address_prefix = var.hub_vm_ip`) or to `var.vpn_subnet_cidr`; give snet-shared its own NSG when it gains residents.

### IN-11: ICMP diagnostics to the hub VM are blocked — port-scoped rules do not match ICMP and the 4000 deny precedes defaults

**File:** `terraform/modules/hub/main.tf:79-89,115-125`
**Issue:** Rules 100/110/120 are port-scoped (ICMP has no ports and will not match), rules 130/140 exclude VNet destinations, and `DenyAllOtherInbound` (4000) fires before default `AllowVnetInBound`. Result: `ping 10.10.0.10` from a spoke test VM or the laptop fails even when DNS works — a predictable time sink during checkpoint verification that looks like an NVA fault.
**Fix:** If intended, document it next to the deny rule; otherwise add an ICMP allow from `10.10.0.0/16`/`var.wg_transfer_cidr`/`var.onprem_address_space` with `protocol = "Icmp"`, `destination_port_range = "*"`.

### IN-12: `resource_provider_registrations = "none"` with no documented list of required resource providers

**File:** `terraform/envs/lab/providers.tf:23`; `terraform/bootstrap/main.tf:22`
**Issue:** Both roots disable automatic RP registration, so a fresh subscription needs Microsoft.Network, Microsoft.Compute, Microsoft.Storage, Microsoft.Consumption, and Microsoft.PrivateDns (plus Microsoft.Resources) pre-registered — but no comment or doc lists them. First apply on a new subscription fails midway with per-resource RP errors.
**Fix:** Add the required RP list (and the one-line `az provider register` loop) as a comment beside each provider block or in the repo docs.

---

_Reviewed: 2026-08-03T14:52:43Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
