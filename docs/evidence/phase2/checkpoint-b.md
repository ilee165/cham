# Phase 2 Checkpoint B Evidence

Captured 2026-08-02T23:41:12-04:00 after the explicitly approved base-lab apply.

## Approved artifact

- Saved plan: `checkpoint-b-ncus-b2ats-v2.tfplan`
- SHA-256: `4edde8bde9dddb3a534756f177380fbd69629dbdf6feb7082cf76204fde0bfd0`
- Apply result: 32 added, 0 changed, 0 destroyed
- Location: North Central US
- Hub size: `Standard_B2ats_v2`

## Live verification

| Check | Sanitized result |
|---|---|
| Terraform state | 32 managed resources |
| Terraform drift | Detailed exit code 0; no changes; 0 warnings; 0 errors |
| Hub VM | Provisioning succeeded; running; expected location and size |
| Hub networking | Private address matches the design; Azure NIC IP forwarding enabled |
| VNet peerings | 4 of 4 Connected with forwarded traffic enabled |
| Cloud-init | Done |
| DNS service | BIND active |
| Guest forwarding | `net.ipv4.ip_forward=1` |
| Hub SNAT | Exactly one expected POSTROUTING MASQUERADE rule |
| Private DNS | Azure-provided DNS and local BIND both resolve the seed record to `10.10.4.20` |
| Private DNS links | 3 Completed; 2 have auto-registration enabled |
| NSGs | 3 present; named allow rules present; hub terminal inbound deny present at priority 4000 |
| Ingress sources | SSH and WireGuard allow rules each use a single `/32`; the address is intentionally omitted |
| WireGuard | Service inactive, as required for Phase 2 |
| Budget | USD 50 monthly budget; enabled thresholds at 50% and 90% |
| Deferred resources | 0 DNS Private Resolver resources; 0 test-VM resources; one hub VM only |

## Capacity and next gate

North Central US `standardBasv2Family` usage is 2 of 4 vCPUs after the base apply. Two simultaneous `Standard_B2ats_v2` verification VMs would require four additional family vCPUs and cannot be applied under the current limit. The explicitly approved request to raise the limit to 6 was rejected by Azure as `ResourceNotAvailableForOffer`; details and the smallest viable alternative are recorded in `checkpoint-c-capacity.md`. No Checkpoint C plan has been generated or applied.

## Sanitization

This evidence intentionally excludes public and home IP addresses, full subscription and tenant identifiers, notification contacts, SSH material, backend identifiers, raw state, raw plan output, and resource IDs.
