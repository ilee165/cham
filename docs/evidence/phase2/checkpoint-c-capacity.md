# Phase 2 Checkpoint C Capacity Evidence

Captured 2026-08-03 during explicitly approved Checkpoint C preparation. A saved test-VM plan was generated for hash review; it was not applied and the hub remained deallocated.

## Requested quota change

- Provider prerequisite: `Microsoft.Quota` registered successfully.
- Scope: Microsoft Compute, North Central US.
- Resource: `standardBasv2Family`.
- Effective usage before and after request: 2 of 4 vCPUs.
- Requested limit: 6 vCPUs.
- Azure accepted the request for processing, then returned `Failed` with `ResourceNotAvailableForOffer`.
- Effective limit remains 4 vCPUs.

Two simultaneous `Standard_B2ats_v2` test VMs therefore remain impossible while the two-vCPU B2ats v2 hub is deployed.

## Read-only alternative analysis

The subscription's North Central US SKU catalog marks every one-vCPU VM SKU with at least 2 GiB of memory as `NotAvailableForSubscription`. The smallest viable x64 alternative found in a separate family is:

| Property | Value |
|---|---|
| Test SKU | `Standard_D2als_v6` |
| Architecture | x64 |
| Memory | 4 GiB |
| Hyper-V generation | V2 |
| Family | `standardDalv6Family` |
| Current family usage | 0 of 4 vCPUs |
| Test pair requirement | 4 vCPUs |
| Current North Central US Linux consumption rate | USD 0.0804 per VM-hour |

Two temporary test VMs would add approximately USD 0.1608 per hour of compute, plus two prorated 30-GiB Standard HDD OS disks and minor variable charges. Including the running base lab, a one-hour verification timebox is conservatively about USD 0.20 before tax and transfer.

The user explicitly approved this SKU for preparation because it differs from the previously approved B2ats v2 test-VM choice. The hub remains `Standard_B2ats_v2`; only the temporary spoke test VMs use `Standard_D2als_v6`. The resulting saved plan is documented in `checkpoint-c-plan.md`; explicit approval of its exact hash remains mandatory before the hub can be started or the plan applied.

## Total Regional Cores correction

The original analysis checked both VM-family quotas but omitted the independent Total Regional Cores limit. During the approved apply, the hub plus app VM consumed the regional limit of 4 of 4 cores. Azure rejected the management VM with `OperationNotAllowed`, reporting that two additional cores and a minimum limit of six were required.

The user then explicitly approved requesting a Total Regional Cores increase from 4 to 6, conditional application of the exact recovery-plan hash only after an effective limit of at least six, and no Checkpoint D destroy. Azure accepted the quota request for processing, then returned terminal `Failed` state with `ResourceNotAvailableForOffer`. The effective limit remains 4 of 4, so the condition was not met: the recovery plan was not applied, neither deallocated VM was started, and no remaining topology test or destroy action ran. The one-create recovery plan and failed gate are documented in `checkpoint-c-recovery.md`.

## Sanitization

This evidence excludes the quota request ID, subscription and tenant identifiers, public and home IP addresses, contacts, SSH material, raw state, and raw API responses.
