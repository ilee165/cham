# Phase 2 Checkpoint C Recovery Evidence

Captured 2026-08-03 after the explicitly approved Checkpoint C apply stopped partway through Azure VM creation, then updated after the approved quota-recovery gate reached a terminal failure.

## Approval and partial apply

- Approved artifact: `checkpoint-c-ncus-d2als-v6.tfplan`.
- Approved SHA-256: `6d532adbf8357e2bdabf6367169424cf0e43de4387d062add61df9eacee6006c`.
- Hub readiness passed before apply: cloud-init done, DNS active, IP forwarding enabled, one SNAT rule present, and WireGuard inactive.
- Created and tracked: app test NIC, management test NIC, and app test VM.
- Not created: management test VM.
- Terraform state after the partial apply: 35 resources.
- DNS Private Resolver remained disabled; no public IP, replacement, delete, or destroy action occurred.

The original saved plan is consumed and stale after the state change. It must not be applied again.

## Capacity root cause

Azure rejected the management VM with `OperationNotAllowed` because the independent North Central US Total Regional Cores quota reached 4 of 4. The hub and app VMs consume four cores even while deallocated; creating the two-core management VM requires a limit of at least six.

The VM-family quotas are not exhausted: BASv2 usage is 2 of 4 and Dalsv6 usage is 2 of 4.

## Approved recovery gate outcome

- The user explicitly approved requesting North Central US Total Regional Cores from 4 to 6.
- Azure accepted the request for processing, then reported terminal `Failed` state with `ResourceNotAvailableForOffer`.
- A fresh usage check still reports Total Regional Cores at 4 of 4; the required effective limit of at least six was never reached.
- The exact recovery plan remained unchanged at SHA-256 `cda9d41188a4c3cb7920208a8fefbf77349d003e3672181cf463afb1325faf35` with 1 create, 1 in-place update, and 0 deletes.
- In accordance with the conditional approval, the plan was not applied, neither deallocated VM was started, no remaining topology test ran, and no Checkpoint D destroy action occurred.

## Bounded app-side tests

| Test | Result |
|---|---|
| App SSH and cloud-init | PASS |
| Default route through hub NVA | PASS |
| On-premises-prefix route through hub NVA | PASS |
| Seed DNS resolution through hub | PASS |
| App Private DNS auto-registration | PASS |
| Seed record remains non-auto | PASS |
| Management record absent while VM absent | PASS |
| App egress equals hub public IP | FAIL — connection timed out before reaching the hub guest |
| App-to-management isolation | BLOCKED — management VM absent |
| Hub-to-management reachability | BLOCKED — management VM absent |

The egress trace showed the UDR and guest configuration were present, but the hub effective NSG had only home WireGuard, home SSH, RFC1918 DNS, and terminal deny rules. No forwarded-transit allow existed. Microsoft guidance for an NVA using a Standard public IP requires an explicit NSG rule permitting routed traffic to the appliance.

## Recovery configuration

The hub NSG now declares two source- and destination-scoped inbound rules ahead of the terminal deny:

- App and management spoke CIDRs to the `Internet` service tag.
- App and management spoke CIDRs to the configured on-premises prefix.

These rules do not allow spoke traffic to arbitrary hub-local services and do not widen the existing home-only SSH or WireGuard rules.

## Saved recovery artifact

| Property | Value |
|---|---|
| File | `checkpoint-c-recovery-regional-cores-nva-nsg.tfplan` |
| SHA-256 | `cda9d41188a4c3cb7920208a8fefbf77349d003e3672181cf463afb1325faf35` |
| Terraform summary | 1 create, 1 in-place update, 0 destroy |
| Create | Management `Standard_D2als_v6` VM only |
| Update | Hub NSG only; adds the two scoped transit rules |
| Terraform warnings | 0 |
| File protection | Gitignored; inherited ACLs removed; access limited to the active user and SYSTEM |

Saved-plan JSON inspection confirmed no resolver, public-IP, replacement, or delete action and no private-key marker.

## Validation and current cost state

- Recursive Terraform formatting passed.
- Bootstrap, lab, and Cloudflare Terraform validation passed.
- TFLint passed with zero issues.
- Checkov passed 52 checks with zero failures and 15 documented skips.
- Fresh post-request verification reports 35 Terraform state resources, the hub and app VMs both `VM deallocated`, the management VM absent, and zero DNS Private Resolver resources.
- VM compute billing is stopped.
- Managed disks, the static public IP, Private DNS, networking usage, and state storage can continue to accrue charges.

## Current gate and next decision

The quota request failed and the recovery apply gate is closed. Before any further Azure mutation, choose and explicitly approve one path:

1. Keep the current deallocated pause.
2. Prepare, but do not apply, a saved Checkpoint D destroy plan for separate hash review and approval.
3. Re-plan capacity, region, or topology after resolving the offer restriction, with a fresh saved-plan review before any apply or VM start.

## Sanitization

This evidence excludes subscription and tenant identifiers, request and correlation IDs, public and home IP addresses, contacts, SSH and WireGuard key material, backend details, raw state, raw plan JSON, packet captures, and raw Azure API responses.
