# Phase 2 Checkpoint C Saved-Plan Evidence

Captured 2026-08-03 after explicit approval to prepare, but not apply, the revised temporary verification workload.

## Approval boundary

- The hub stayed deallocated throughout preparation.
- No Azure resource was started, created, changed, or destroyed.
- DNS Private Resolver remained disabled.
- Applying the saved plan requires separate approval of the exact SHA-256 below.
- Checkpoint D destroy planning and execution remain separate approval gates.

## Saved artifact

| Property | Value |
|---|---|
| File | `checkpoint-c-ncus-d2als-v6.tfplan` |
| SHA-256 | `6d532adbf8357e2bdabf6367169424cf0e43de4387d062add61df9eacee6006c` |
| Terraform summary | 4 create, 0 change, 0 destroy |
| Terraform warnings | 0 |
| Existing resources | 32 no-op |
| File protection | Gitignored; inherited ACLs removed; access limited to the active user and SYSTEM |

## Planned delta

- Two private network interfaces: one in the app spoke and one in the management spoke.
- Two x64 Ubuntu Linux VMs using `Standard_D2als_v6`, 2 vCPUs and 4 GiB each.
- Two 30-GiB Standard_LRS OS disks created with the VMs.
- VM extension operations explicitly disabled.
- Zero public-IP additions, hub changes, resolver resources, replacements, updates, or deletes.

The hub input remains `Standard_B2ats_v2`. Only the temporary spoke test-VM input is `Standard_D2als_v6`.

## Capacity and cost gate

- Dalsv6-family quota before apply: 0 of 4 vCPUs.
- Planned test pair: 4 vCPUs, consuming the available family quota exactly.
- Current Azure Linux consumption rate: USD 0.0804 per VM-hour, or USD 0.1608 per hour for the pair.
- Two prorated Standard HDD disks and variable network, DNS, operation, tax, and transfer charges are additional.
- A one-hour run with the hub started is conservatively budgeted at about USD 0.20; stop and cleanup should begin immediately after the timeboxed checks.

## Validation

- Recursive Terraform formatting passed.
- Bootstrap, lab, and Cloudflare Terraform validation passed.
- TFLint passed with zero issues.
- Checkov passed 52 checks with zero failures and 15 documented skips.
- Saved-plan JSON inspection confirmed four creates and no other actionable change.
- No private-key marker is present in the saved-plan JSON.

## Execution result

The user explicitly approved this exact artifact. Its apply partially completed: both private NICs and the app test VM succeeded, while Azure rejected the management test VM because the independent Total Regional Cores quota reached 4 of 4 and the additional VM required a six-core limit. Terraform now tracks 35 resources.

The original saved plan is consumed and stale after that state change. It must not be retried. Both running VMs were deallocated after bounded diagnostics, no DNS Private Resolver or destroy action occurred, and recovery evidence is recorded in `checkpoint-c-recovery.md`.

## Sanitization

This evidence excludes subscription and tenant identifiers, public and home IP addresses, contacts, SSH and WireGuard key material, backend details, raw state, raw plan JSON, and raw Azure API responses.
