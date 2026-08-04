# Phase 2 Checkpoint C Four-Core Recovery Plan

Prepared 2026-08-03 after the operator directed completion of Checkpoint C.
The operator later approved the exact saved-plan hash. Terraform attempted that
plan, but Azure rejected the app VM resize because `Standard_B1ms` had no
regional capacity. The hub NSG update completed before the resize failed. No VM
was started and the management VM was not created.

## Immutable source and approval boundary

- Source commit: `a390a2d49965822cf7d26bcca02253330459ebdf`.
- Original saved plan: `checkpoint-c-four-core-b1ms.tfplan`.
- SHA-256: `4d4447b67c3d4c40f6f79e3ff617efb85cb97b13f0ee7a82cc9e0722c9fb3ed3`.
- The plan is gitignored and ACL-restricted to the active user and SYSTEM.
- The operator explicitly approved this exact hash and the associated bounded
  start, test, and deallocation sequence.
- The apply attempt consumed the artifact. It is now named
  `FAILED-DO-NOT-RETRY-checkpoint-c-four-core-b1ms.tfplan`; its SHA-256 remains
  unchanged. Never apply it again.

## Capacity recovery

- North Central US Total Regional Cores remains 4 of 4.
- The existing hub uses two vCPUs. The app VM currently uses two vCPUs even
  while deallocated; the management VM is absent.
- `Standard_B1ms` is one vCPU and 2 GiB. It appeared in the existing app VM's
  Azure resize-options response, and its `standardBSFamily` quota was 0 of 4.
  That response proved insufficient: the apply returned `SkuNotAvailable` for
  a North Central US capacity restriction.
- Both temporary VMs use `Standard_B1ms`, yielding two hub cores plus one app
  core plus one management core: exactly four regional cores.
- Terraform has an explicit management-module dependency on the app module.
  The saved apply graph contains a direct management-to-app edge, so the app
  resize completes before Azure evaluates the management VM create.

## Saved-plan delta

Terraform reports **1 add, 2 in-place changes, 0 destroy, 0 replacement**:

1. Update the hub NSG in place with the four reviewed, scoped transit rules.
2. Resize the deallocated app VM in place from `Standard_D2als_v6` to
   `Standard_B1ms`.
3. Create the management `Standard_B1ms` VM on its existing private NIC.

The hub VM, both test NICs, routes, peerings, public IP, disks already in
state, and all other resources are unchanged. The plan contains no DNS Private
Resolver change, no public-IP change, and no delete or replacement action.
Terraform emitted zero warnings and zero errors.

## Approved apply outcome

- Apply started at `2026-08-03T20:46:59Z` and exited unsuccessfully at
  `2026-08-03T20:47:15Z`.
- The hub NSG update completed. All four reviewed rules are present:
  `AllowInternetTransitFromSpokes`, `AllowOnPremTransitFromSpokes`,
  `AllowOutboundForwardedToSpokes`, and
  `AllowWgTransferTransitFromSpokes`.
- Azure returned HTTP 409 `SkuNotAvailable` while resizing `vm-test-app` to
  `Standard_B1ms` because of North Central US capacity restrictions.
- The explicit Terraform dependency prevented the management VM create from
  being attempted after the resize failed.
- `vm-test-app` remains `Standard_D2als_v6` and deallocated.
- `vm-hub-ddi` remains `Standard_B2ats_v2` and deallocated.
- `vm-test-mgmt` remains absent. Its unattached NIC remains provisioned.
- Terraform state still tracks 35 resources. Total Regional vCPU usage remains
  4 of 4, Standard BS Family usage remains 0 of 4, and the DNS Private Resolver
  count remains zero.
- A subscription-scoped Azure Resource SKUs query found zero unrestricted
  one-vCPU VM SKUs in North Central US. It also found zero unrestricted
  constrained-vCPU SKUs exposing one usable vCPU.

## Cost and timebox

The Microsoft Azure Retail Prices API returned North Central US Linux
consumption rates of USD 0.0208/hour for each `Standard_B1ms` VM and USD
0.0094/hour for the `Standard_B2ats_v2` hub VM. Compute during the paired test
window is therefore about USD 0.051/hour. A conservative one-hour ceiling is
USD 0.08 before taxes and variable disk, operation, DNS, and transfer charges.

The one-hour clock begins when the management VM is created by the approved
apply. Start the deallocated hub and app VMs immediately, run only the bounded
topology checks, and deallocate all three VMs afterward. Stop before any
Checkpoint D destroy.

The management VM was never created, so the one-hour clock never began. No VM
compute was started. Deallocated VMs do not incur compute charges, although
retained disks, the static public IP, DNS, storage, and data operations can
still accrue charges.

## Post-approval test set

1. Confirm cloud-init and SSH on both test VMs.
2. Confirm both effective route tables use the hub NVA for default and
   on-premises prefixes.
3. Confirm hub DNS and seed-record resolution from both spokes.
4. Confirm both VM records auto-register and the seed remains non-auto.
5. Confirm app and management egress both match the hub public IP, recording
   only boolean matches.
6. Confirm app-to-management traffic fails.
7. Confirm hub-to-management traffic succeeds.
8. Confirm home-only ingress, WireGuard disabled, and the effective NSG rules.

None of these post-approval tests ran because the prerequisite apply failed.
Checkpoint C is therefore still incomplete. Completing the original
simultaneous three-VM topology now requires new capacity, a different region or
subscription, or a materially different test topology. Each option requires a
fresh saved plan and separate approval. No Checkpoint D destroy was attempted.

## Region capacity probe and selected recovery (2026-08-03)

After the `SkuNotAvailable` failure, read-only probes ran with
`az vm list-skus` and `az vm list-usage` across eastus, eastus2, centralus,
southcentralus, westus2, and westus3:

- Total Regional vCPUs limit is 4 with 0 used in every probed region. The
  North Central US limit-raise denial (`ResourceNotAvailableForOffer`) makes
  any quota-dependent design fragile for this subscription offer.
- No x86 B-family SKU is offered to this subscription in any probed region;
  only ARM64 `B*p*_v2` sizes appear (centralus, southcentralus, westus2). The
  original `Standard_B1ms`/`Standard_B2ats_v2` design is not portable.
- Unrestricted one-vCPU x86 SKUs exist elsewhere: `Standard_F1als_v7` and
  other `F1a*_v7` variants plus `Standard_DC1s_v3`/`DC1ds_v3` in eastus,
  eastus2, centralus, southcentralus, and westus2. westus3 offers none of the
  probed families.
- eastus2 additionally offers the Dals v6/v7 families. `Standard_D2als_v6`
  carries a zone-2-only restriction (regional deployment unaffected), but
  eastus2 publishes no `Dalsv6` family quota row, so v6 reuse risks a quota
  denial. The v7 rows `Standard Dalsv7 Family vCPUs` and
  `Standard Falsv7 Family vCPUs` both show limit 4 with 0 used.
- `Standard_D2als_v7` (2 vCPU, 4 GiB) and `Standard_F1als_v7` (1 vCPU, 2 GiB)
  both report `DiskControllerTypes: NVMe` only, so every v7 VM must set
  `disk_controller_type = "NVMe"`. The Canonical `ubuntu-24_04-lts:server`
  image reports `SCSI, NVMe` support with Hyper-V generation V2, so the
  existing image reference remains valid.

The operator selected the eastus2 rebuild: hub `Standard_D2als_v7` (two
cores) plus app and management `Standard_F1als_v7` (one core each) — exactly
four regional cores, no quota increase, full simultaneous three-VM validation
semantics, and no resize step anywhere in the sequence. Recovery order:

1. Approve and apply a saved Checkpoint D destroy plan for the 35-resource
   North Central US lab stack.
2. Regenerate Checkpoint B in eastus2 from the updated configuration.
3. Run Checkpoint C with all three VMs created at their final sizes.

The 6-resource bootstrap stack and the subscription budget are
region-independent and are retained. The hub public IP will change with the
region move.
